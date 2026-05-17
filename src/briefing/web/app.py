from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from briefing.config import AppConfig
from briefing.web.i18n import get_translator

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
FAVICON_PATH = STATIC_DIR / "favicon.svg"


def create_app(config: AppConfig | None = None) -> FastAPI:
    app = FastAPI(title="Daily Briefing")
    app.state.config = config

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return FileResponse(FAVICON_PATH, media_type="image/svg+xml")

    # i18n — inject _() translator and current_lang into all templates
    lang = config.language if config else "en"
    app.state.templates.env.globals["_"] = get_translator(lang)
    app.state.templates.env.globals["current_lang"] = lang
    app.state.templates.env.globals["theme"] = config.theme if config else "light"

    from briefing.llm.models import PROVIDER_META
    app.state.templates.env.globals["provider_meta"] = PROVIDER_META

    from briefing.web.routes.dashboard import router as dashboard_router
    from briefing.web.routes.portfolio import router as portfolio_router
    from briefing.web.routes.briefings import router as briefings_router
    from briefing.web.routes.settings import router as settings_router
    from briefing.web.routes.newsmap import router as newsmap_router
    from briefing.web.routes.tts import router as tts_router

    app.include_router(dashboard_router)
    app.include_router(portfolio_router)
    app.include_router(briefings_router)
    app.include_router(settings_router)
    app.include_router(newsmap_router)
    app.include_router(tts_router)

    return app
