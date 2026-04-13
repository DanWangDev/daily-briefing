from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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
    # Per-provider model fields
    anthropic_model: str = Form("claude-haiku-4-5-20251001"),
    openai_model: str = Form("gpt-4o-mini"),
    ollama_model: str = Form("llama3"),
    qwen_model: str = Form("qwen-plus"),
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

    # LLM - set provider and the model for that provider
    config.llm.provider = llm_provider
    model_map = {
        "anthropic": anthropic_model,
        "openai": openai_model,
        "ollama": ollama_model,
        "qwen": qwen_model,
    }
    config.llm.model = model_map.get(llm_provider, anthropic_model)
    base_url_map = {
        "ollama": ollama_base_url,
        "qwen": qwen_base_url,
    }
    config.llm.base_url = base_url_map.get(llm_provider, config.llm.base_url)

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
