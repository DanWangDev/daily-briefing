"""Text-to-speech endpoint using Edge TTS (Microsoft neural voices)."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import edge_tts
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache generated audio files to avoid re-generating
_CACHE_DIR = Path("data/tts_cache")


@router.post("/api/tts")
async def generate_tts(request: Request):
    """Generate speech from text and return audio URL."""
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    # Truncate very long text
    if len(text) > 5000:
        text = text[:5000]

    config = request.app.state.config
    lang = config.language if config else "en"

    # Voice selection: use configured voice or default
    voice = getattr(config, "tts_voice", "") or ""
    if not voice:
        voice = "zh-CN-XiaoxiaoNeural" if lang == "zh" else "en-US-AriaNeural"

    # Cache key based on text + voice
    cache_key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / f"{cache_key}.mp3"

    if not cache_path.exists():
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(cache_path))
        except Exception as e:
            logger.error("Edge TTS failed: %s", e)
            return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"url": f"/api/tts/audio/{cache_key}.mp3"})


@router.get("/api/tts/audio/{filename}")
async def serve_tts_audio(filename: str):
    """Serve cached TTS audio file."""
    path = _CACHE_DIR / filename
    if not path.exists() or not path.suffix == ".mp3":
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/api/tts/voices")
async def list_voices():
    """List available Edge TTS voices for settings UI."""
    voices = await edge_tts.list_voices()
    result = []
    for v in voices:
        locale = v.get("Locale", "")
        if locale.startswith("en-US") or locale.startswith("zh-CN") or locale.startswith("zh-HK"):
            result.append({
                "id": v["ShortName"],
                "name": v.get("FriendlyName", v["ShortName"]),
                "gender": v.get("Gender", ""),
                "locale": locale,
            })
    return result
