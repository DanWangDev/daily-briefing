"""Text-to-speech endpoint using Kokoro (ONNX) with misaki for Chinese G2P."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from threading import Lock

import httpx
import numpy as np
import soundfile as sf
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_CACHE_DIR = Path("data/tts_cache")
_MODEL_DIR = Path("data/kokoro_models")
_MODEL_PATH = _MODEL_DIR / "kokoro-v1.0.onnx"
_VOICES_PATH = _MODEL_DIR / "voices-v1.0.bin"
_MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)
_SAMPLE_RATE = 24_000
_SEGMENT_GAP_SECONDS = 0.15

# Preset id -> (display label, english voice id, mandarin voice id).
# Each preset is one "voice identity" that works for both English (via
# kokoro-onnx's espeak backend) and Mandarin (via misaki's pypinyin+jieba G2P
# feeding Kokoro's IPA phoneme input).
VOICE_PRESETS: dict[str, tuple[str, str, str]] = {
    "female_warm":    ("Female — Warm (女 · 温暖)",    "af_bella",   "zf_xiaoxiao"),
    "female_bright":  ("Female — Bright (女 · 明亮)",  "af_heart",   "zf_xiaoni"),
    "female_calm":    ("Female — Calm (女 · 柔和)",    "af_sarah",   "zf_xiaoyi"),
    "male_warm":      ("Male — Warm (男 · 温暖)",      "am_adam",    "zm_yunyang"),
    "male_calm":      ("Male — Calm (男 · 沉稳)",      "am_michael", "zm_yunjian"),
    "male_energetic": ("Male — Energetic (男 · 活力)", "am_echo",    "zm_yunxi"),
}
_DEFAULT_PRESET = "female_warm"

_CONTROL_TOKEN_RE = re.compile(r"\[(?:laugh|uv_break|lbreak|break|oral)(?:_\d+)?\]")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_INVALID_PUNCT_RE = re.compile(r"[()\[\]{}<>*~|\\^_＾＊〈〉《》【】「」『』]")
_MULTI_SPACE_RE = re.compile(r"\s{2,}")

_FULLWIDTH_MAP = str.maketrans({
    "（": " ", "）": " ",
    "：": ":", "；": ";",
    "，": ",", "。": ".",
    "！": "!", "？": "?",
    "－": "-", "％": "%",
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "、": ",",
})

_kokoro = None
_zh_g2p = None
_init_lock = Lock()


def _cleanup_legacy_cache() -> None:
    try:
        if _CACHE_DIR.exists():
            for old in _CACHE_DIR.glob("*.mp3"):
                old.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Legacy TTS cache cleanup skipped: %s", exc)


_cleanup_legacy_cache()


def _download_file(url: str, dest: Path) -> None:
    logger.info("Downloading %s → %s", dest.name, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=None) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        next_log = 1 << 25  # log every ~32MB
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=1 << 20):
                fh.write(chunk)
                downloaded += len(chunk)
                if total and downloaded >= next_log:
                    logger.info(
                        "  %s %.0f%% (%d / %d MB)",
                        dest.name,
                        downloaded * 100 / total,
                        downloaded >> 20,
                        total >> 20,
                    )
                    next_log += 1 << 25
    tmp.replace(dest)
    logger.info("  %s done (%d MB)", dest.name, downloaded >> 20)


def _ensure_models() -> None:
    for url, path in ((_MODEL_URL, _MODEL_PATH), (_VOICES_URL, _VOICES_PATH)):
        if not path.exists():
            _download_file(url, path)


def _get_kokoro():
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    with _init_lock:
        if _kokoro is not None:
            return _kokoro
        _ensure_models()
        from kokoro_onnx import Kokoro

        logger.info("Loading Kokoro ONNX model…")
        _kokoro = Kokoro(str(_MODEL_PATH), str(_VOICES_PATH))
        logger.info("Kokoro ready.")
        return _kokoro


def _get_zh_g2p():
    global _zh_g2p
    if _zh_g2p is not None:
        return _zh_g2p
    with _init_lock:
        if _zh_g2p is not None:
            return _zh_g2p
        from misaki import zh as misaki_zh

        logger.info("Loading misaki Chinese G2P (jieba + pypinyin)…")
        _zh_g2p = misaki_zh.ZHG2P()
        logger.info("misaki G2P ready.")
        return _zh_g2p


def _sanitize(text: str) -> str:
    text = _CONTROL_TOKEN_RE.sub("", text)
    text = text.translate(_FULLWIDTH_MAP)
    text = _INVALID_PUNCT_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def _resolve_preset(config) -> tuple[str, str, str]:
    preset_id = (getattr(config, "tts_voice", "") or _DEFAULT_PRESET).strip()
    if preset_id not in VOICE_PRESETS:
        preset_id = _DEFAULT_PRESET
    _label, en_voice, zh_voice = VOICE_PRESETS[preset_id]
    return preset_id, en_voice, zh_voice


def _is_cjk(ch: str) -> bool:
    return bool(_CJK_CHAR_RE.match(ch))


def _segment_by_language(text: str) -> list[tuple[str, str]]:
    """Split text into consecutive (lang, run) pairs.

    Kokoro routes each run through a different synthesis path (misaki for zh,
    espeak for en), so monolingual runs are required. Only consecutive
    same-language runs are merged — never cross-language — because absorbing
    a short foreign-script run into a neighbour would mispronounce it
    (English words read by misaki, or CJK chars read by espeak).
    """
    if not text:
        return []

    runs: list[tuple[str, list[str]]] = []
    current: str | None = None
    for ch in text:
        # Only letters and CJK characters classify the run's language.
        # Digits and punctuation are "neutral": they attach to whichever
        # run is currently active. This keeps "947亿美元" as a single zh
        # run (so misaki reads 947 as 九百四十七) instead of splitting
        # the digits into their own en segment.
        if not (ch.isalpha() or _is_cjk(ch)):
            if runs:
                runs[-1][1].append(ch)
            continue
        lang = "zh" if _is_cjk(ch) else "en"
        if lang == current and runs:
            runs[-1][1].append(ch)
        else:
            runs.append((lang, [ch]))
            current = lang

    merged: list[tuple[str, str]] = []
    for lang, chars in runs:
        seg = "".join(chars).strip()
        if not seg:
            continue
        if merged and merged[-1][0] == lang:
            prev_lang, prev_seg = merged[-1]
            merged[-1] = (prev_lang, f"{prev_seg} {seg}".strip())
        else:
            merged.append((lang, seg))
    return merged


def _synthesize_sync(text: str, en_voice: str, zh_voice: str) -> np.ndarray:
    kokoro = _get_kokoro()
    segments = _segment_by_language(text)
    if not segments:
        return np.zeros(0, dtype=np.float32)

    gap = np.zeros(int(_SEGMENT_GAP_SECONDS * _SAMPLE_RATE), dtype=np.float32)
    parts: list[np.ndarray] = []

    for idx, (lang, segment) in enumerate(segments):
        if not segment.strip():
            continue
        if lang == "zh":
            g2p = _get_zh_g2p()
            phonemes = g2p(segment)
            if not phonemes:
                continue
            samples, _sr = kokoro.create(
                phonemes,
                voice=zh_voice,
                speed=1.0,
                lang="cmn",
                is_phonemes=True,
            )
        else:
            samples, _sr = kokoro.create(
                segment,
                voice=en_voice,
                speed=1.0,
                lang="en-us",
                is_phonemes=False,
            )
        parts.append(np.asarray(samples, dtype=np.float32))
        if idx < len(segments) - 1:
            parts.append(gap)

    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


@router.post("/api/tts")
async def generate_tts(request: Request):
    """Generate speech from text and return audio URL."""
    body = await request.json()
    text = _sanitize(body.get("text", ""))
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    if len(text) > 5000:
        text = text[:5000]

    config = request.app.state.config
    preset_id, en_voice, zh_voice = _resolve_preset(config)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(f"kokoro-v1:{preset_id}:{text}".encode()).hexdigest()
    cache_path = _CACHE_DIR / f"{cache_key}.wav"

    if not cache_path.exists():
        try:
            audio = await asyncio.to_thread(
                _synthesize_sync, text, en_voice, zh_voice
            )
            if audio.size == 0:
                return JSONResponse(
                    {"error": "Empty synthesis output"}, status_code=500
                )
            sf.write(str(cache_path), audio, _SAMPLE_RATE, subtype="PCM_16")
        except Exception as exc:
            logger.exception("Kokoro synthesis failed")
            return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse({"url": f"/api/tts/audio/{cache_key}.wav"})


@router.get("/api/tts/audio/{filename}")
async def serve_tts_audio(filename: str):
    """Serve cached TTS audio file."""
    path = _CACHE_DIR / filename
    if not path.exists() or path.suffix != ".wav":
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(path, media_type="audio/wav")


@router.get("/api/tts/voices")
async def list_voices():
    """List available voice presets for settings UI."""
    return [
        {
            "id": pid,
            "name": label,
            "gender": "male" if pid.startswith("male") else "female",
        }
        for pid, (label, _en, _zh) in VOICE_PRESETS.items()
    ]
