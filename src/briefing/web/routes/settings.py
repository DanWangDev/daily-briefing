from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from briefing.database import get_session
from briefing.settings_store import save_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    config = request.app.state.config
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"config": config},
    )


@router.get("/api/models")
async def list_models(request: Request, provider: str = Query(...)):
    """Return available models for *provider* from its live API."""
    from briefing.llm.models import fetch_models

    from briefing.llm.models import PROVIDER_META

    config = request.app.state.config
    llm = config.llm

    api_key = llm.get_api_key(provider) or ""
    # Use the stored base_url only if it belongs to the active provider;
    # otherwise fall back to the provider's default.
    pmeta = PROVIDER_META.get(provider, {})
    default_base = pmeta.get("default_base_url", "")
    base_url = llm.base_url if llm.provider == provider else default_base

    models, error = await fetch_models(
        provider,
        api_key=api_key,
        base_url=base_url,
    )
    return JSONResponse({"models": models, "error": error})


@router.post("/api/settings", response_class=HTMLResponse)
async def update_settings(
    request: Request,
    language: str = Form("en"),
    theme: str = Form("light"),
    tts_voice: str = Form(""),
    timezone: str = Form("America/New_York"),
    delivery_time: str = Form("07:00"),
    email_enabled: bool = Form(False),
    llm_provider: str = Form("anthropic"),
    model: str = Form(""),
    # Per-provider config
    anthropic_api_key: str = Form(""),
    openai_api_key: str = Form(""),
    ollama_base_url: str = Form("http://localhost:11434"),
    qwen_api_key: str = Form(""),
    qwen_base_url: str = Form("https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    # Data source keys
    newsapi_key: str = Form(""),
    alpha_vantage_key: str = Form(""),
    massive_key: str = Form(""),
    # Email
    smtp_host: str = Form("smtp.gmail.com"),
    smtp_port: int = Form(587),
    from_address: str = Form(""),
    to_address: str = Form(""),
    email_user: str = Form(""),
    email_pass: str = Form(""),
):
    config = request.app.state.config

    # Language, theme & TTS
    config.language = language
    config.theme = theme
    config.tts_voice = tts_voice

    # Schedule
    config.schedule.timezone = timezone
    config.schedule.delivery_time = delivery_time
    config.schedule.email_enabled = email_enabled

    # LLM - set provider and model
    config.llm.provider = llm_provider
    if model.strip():
        config.llm.model = model.strip()

    base_url_map = {
        "ollama": ollama_base_url,
        "qwen": qwen_base_url,
    }
    if llm_provider in base_url_map:
        config.llm.base_url = base_url_map[llm_provider]

    # LLM API keys (only update if non-empty - blank means keep current)
    if anthropic_api_key.strip():
        config.llm.set_api_key("anthropic", anthropic_api_key.strip())
    if openai_api_key.strip():
        config.llm.set_api_key("openai", openai_api_key.strip())
    if qwen_api_key.strip():
        config.llm.set_api_key("qwen", qwen_api_key.strip())

    # Data source API keys
    if newsapi_key.strip():
        config.api_keys.set_key("newsapi", newsapi_key.strip())
    if alpha_vantage_key.strip():
        config.api_keys.set_key("alpha_vantage", alpha_vantage_key.strip())
    if massive_key.strip():
        config.api_keys.set_key("massive", massive_key.strip())

    # Email
    config.email.smtp_host = smtp_host
    config.email.smtp_port = smtp_port
    config.email.from_address = from_address
    config.email.to_address = to_address

    # Email credentials
    if email_user.strip():
        config.email.set_credential("username", email_user.strip())
    if email_pass.strip():
        config.email.set_credential("password", email_pass.strip())

    # Persist all settings to database
    with get_session() as session:
        save_settings(session, config)

    # Restart scheduler with new settings
    from briefing.scheduler import reschedule
    try:
        reschedule(config)
    except Exception as e:
        logger.warning("Failed to reschedule: %s", e)

    # Refresh i18n translator
    from briefing.web.i18n import get_translator, load_translations
    load_translations.cache_clear()
    request.app.state.templates.env.globals["_"] = get_translator(config.language)
    request.app.state.templates.env.globals["current_lang"] = config.language
    request.app.state.templates.env.globals["theme"] = config.theme

    return RedirectResponse("/settings", status_code=303)
