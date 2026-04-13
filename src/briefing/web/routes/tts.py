"""Text-to-speech endpoint using ChatTTS (local neural bilingual TTS)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from threading import Lock

import numpy as np
import soundfile as sf
import torch
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_CACHE_DIR = Path("data/tts_cache")
_SAMPLE_RATE = 24_000

VOICE_PRESETS: dict[str, tuple[str, int]] = {
    "female_soft":    ("Female — Soft (女 · 柔和)",    3333),
    "female_bright":  ("Female — Bright (女 · 明亮)",  4099),
    "female_neutral": ("Female — Neutral (女 · 自然)", 5099),
    "male_warm":      ("Male — Warm (男 · 温暖)",      2222),
    "male_calm":      ("Male — Calm (男 · 沉稳)",      6653),
    "male_energetic": ("Male — Energetic (男 · 活力)", 7869),
}
_DEFAULT_PRESET = "female_soft"

_CONTROL_TOKEN_RE = re.compile(r"\[(?:laugh|uv_break|lbreak|break|oral)(?:_\d+)?\]")

_chat = None
_chat_lock = Lock()


def _cleanup_legacy_cache() -> None:
    try:
        if _CACHE_DIR.exists():
            for old in _CACHE_DIR.glob("*.mp3"):
                old.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Legacy TTS cache cleanup skipped: %s", exc)


_cleanup_legacy_cache()


def _get_chat():
    global _chat
    if _chat is not None:
        return _chat
    with _chat_lock:
        if _chat is not None:
            return _chat
        import ChatTTS

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading ChatTTS model on %s (first run downloads ~1.5GB)…", device)
        chat = ChatTTS.Chat()
        chat.load(compile=False)
        _chat = chat
        logger.info("ChatTTS ready.")
        return _chat


def _sanitize(text: str) -> str:
    return _CONTROL_TOKEN_RE.sub("", text).strip()


def _resolve_preset(config) -> tuple[str, int]:
    preset_id = (getattr(config, "tts_voice", "") or _DEFAULT_PRESET).strip()
    if preset_id not in VOICE_PRESETS:
        preset_id = _DEFAULT_PRESET
    return preset_id, VOICE_PRESETS[preset_id][1]


def _synthesize_sync(text: str, seed: int) -> np.ndarray:
    chat = _get_chat()
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
    wavs = chat.infer([text], use_decoder=True)
    return np.asarray(wavs[0], dtype=np.float32)


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
    preset_id, seed = _resolve_preset(config)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(f"chattts:{preset_id}:{text}".encode()).hexdigest()
    cache_path = _CACHE_DIR / f"{cache_key}.wav"

    if not cache_path.exists():
        try:
            audio = await asyncio.to_thread(_synthesize_sync, text, seed)
            sf.write(str(cache_path), audio, _SAMPLE_RATE, subtype="PCM_16")
        except Exception as exc:
            logger.exception("ChatTTS synthesis failed")
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
        for pid, (label, _seed) in VOICE_PRESETS.items()
    ]
