"""Provider metadata and live model-discovery functions."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static provider metadata (no model names — those come from live APIs)
# ---------------------------------------------------------------------------

PROVIDER_META: dict[str, dict] = {
    "anthropic": {
        "display": "Anthropic (Claude)",
        "requires_api_key": True,
        "key_placeholder": "sk-ant-...",
    },
    "openai": {
        "display": "OpenAI",
        "requires_api_key": True,
        "key_placeholder": "sk-...",
    },
    "qwen": {
        "display": "Alibaba Cloud (Qwen)",
        "requires_api_key": True,
        "key_placeholder": "sk-...",
        "has_base_url": True,
        "default_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    },
    "ollama": {
        "display": "Ollama (Local)",
        "requires_api_key": False,
        "has_base_url": True,
        "default_base_url": "http://localhost:11434",
        "hint_key": "settings.ollama_hint",
    },
    "deepseek": {
        "display": "DeepSeek",
        "requires_api_key": True,
        "key_placeholder": "sk-...",
        "has_base_url": True,
        "default_base_url": "https://api.deepseek.com/v1",
    },
}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

async def fetch_models(
    provider: str,
    *,
    api_key: str = "",
    base_url: str = "",
) -> tuple[list[dict], str | None]:
    """Return (models, error) for *provider*.

    models: ``[{"id": str, "display": str}, ...]``
    error:  human-readable string on failure, or None on success.
    """
    if provider not in PROVIDER_META:
        return [], f"Unknown provider: {provider}"

    meta = PROVIDER_META[provider]
    if meta.get("requires_api_key") and not api_key.strip():
        return [], "API key required"

    try:
        if provider == "anthropic":
            result = await _fetch_anthropic(api_key)
        elif provider == "openai":
            result = await _fetch_openai(api_key)
        elif provider == "qwen":
            fallback = meta.get("default_base_url", "")
            result = await _fetch_qwen(api_key, base_url or fallback)
        elif provider == "deepseek":
            fallback = meta.get("default_base_url", "")
            result = await _fetch_deepseek(api_key, base_url or fallback)
        elif provider == "ollama":
            result = await _fetch_ollama(base_url or meta.get("default_base_url", ""))
        else:
            return [], f"Unknown provider: {provider}"
        return result, None
    except Exception as exc:
        logger.warning("Failed to fetch %s models: %s", provider, exc)
        return [], f"Failed to fetch models: {exc}"


# ---------------------------------------------------------------------------
# Per-provider fetchers
# ---------------------------------------------------------------------------

async def _fetch_anthropic(api_key: str) -> list[dict]:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    models: list[dict] = []
    page = await client.models.list(limit=100)
    for model in page.data:
        if model.type == "model" and model.display_name:
            models.append({"id": model.id, "display": model.display_name})
    models.sort(key=lambda m: m["display"].lower())
    return models


async def _fetch_openai(api_key: str) -> list[dict]:
    import openai

    # Prefixes for chat / language models; excludes embeddings, audio, image, etc.
    _CHAT_PREFIXES = (
        "gpt-", "o1", "o3", "o4", "o1-", "o3-", "o4-",
        "chatgpt-", "ft:gpt-",
    )
    _EXCLUDE = ("dall-e", "whisper", "tts", "text-embedding", "babbage", "davinci")

    client = openai.AsyncOpenAI(api_key=api_key)
    models: list[dict] = []
    page = await client.models.list()
    for model in page.data:
        lid = model.id.lower()
        if any(lid.startswith(p) for p in _CHAT_PREFIXES) and not any(
            lid.startswith(e) for e in _EXCLUDE
        ):
            models.append({"id": model.id, "display": model.id})
    models.sort(key=lambda m: m["display"].lower())
    return models


async def _fetch_qwen(api_key: str, base_url: str) -> list[dict]:
    import openai

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    models: list[dict] = []
    page = await client.models.list()
    for model in page.data:
        models.append({"id": model.id, "display": model.id})
    models.sort(key=lambda m: m["display"].lower())
    return models


async def _fetch_deepseek(api_key: str, base_url: str) -> list[dict]:
    import openai

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    models: list[dict] = []
    page = await client.models.list()
    for model in page.data:
        models.append({"id": model.id, "display": model.id})
    models.sort(key=lambda m: m["display"].lower())
    return models


async def _fetch_ollama(base_url: str) -> list[dict]:
    url = base_url.rstrip("/") + "/api/tags"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    raw = data.get("models", [])
    models = [
        {"id": m["name"], "display": m["name"]}
        for m in raw
        if m.get("name")
    ]
    models.sort(key=lambda m: m["display"].lower())
    return models
