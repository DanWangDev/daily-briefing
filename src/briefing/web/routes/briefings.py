from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from briefing.database import get_session
from briefing.models import Briefing, BriefingSection, Holding

logger = logging.getLogger(__name__)
router = APIRouter()

# Track in-flight generation task so we don't launch duplicates
_generation_task: asyncio.Task | None = None


@router.get("/briefings", response_class=HTMLResponse)
async def briefings_list(request: Request):
    session = get_session()
    try:
        briefings = (
            session.query(Briefing)
            .order_by(Briefing.generated_at.desc())
            .limit(30)
            .all()
        )
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request=request,
            name="briefings.html",
            context={"briefings": briefings},
        )
    finally:
        session.close()


@router.get("/briefings/{briefing_id}", response_class=HTMLResponse)
async def briefing_detail(request: Request, briefing_id: int):
    session = get_session()
    try:
        briefing = session.query(Briefing).filter(Briefing.id == briefing_id).first()
        sections = []
        if briefing:
            sections = (
                session.query(BriefingSection)
                .filter(BriefingSection.briefing_id == briefing.id)
                .all()
            )
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request=request,
            name="briefing_detail.html",
            context={"briefing": briefing, "sections": sections},
        )
    finally:
        session.close()


@router.post("/api/briefings/generate", response_class=HTMLResponse)
async def generate_briefing(request: Request):
    """Trigger a manual briefing generation (non-blocking)."""
    global _generation_task

    config = request.app.state.config

    # Guard: don't launch if already generating
    if _generation_task is not None and not _generation_task.done():
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request=request,
            name="partials/generation_status.html",
            context={"status": "pending"},
        )

    # Verify portfolio has holdings
    session = get_session()
    try:
        if not session.query(Holding).count():
            return HTMLResponse(
                '<article style="text-align:center;padding:2rem;">'
                '<h3>No holdings</h3><p>Add tickers in '
                '<a href="/portfolio">Portfolio</a> first.</p></article>'
            )
    finally:
        session.close()

    # Launch generation in background
    _generation_task = asyncio.create_task(_run_generation(config))

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="partials/generation_status.html",
        context={"status": "pending"},
    )


async def _run_generation(config) -> None:
    """Background wrapper — logs errors; run_briefing handles status updates."""
    from briefing.pipeline.orchestrator import run_briefing

    try:
        briefing_id = await run_briefing(config)
        logger.info("Background generation completed: briefing #%d", briefing_id)
    except Exception as e:
        logger.error("Background generation failed: %s", e)


@router.get("/api/briefings/status", response_class=HTMLResponse)
async def generation_status(request: Request):
    """Poll endpoint — returns progress partial or final briefing content."""
    session = get_session()
    try:
        latest = (
            session.query(Briefing)
            .order_by(Briefing.generated_at.desc())
            .first()
        )
        if not latest:
            return HTMLResponse("<p>No briefings yet.</p>")

        templates = request.app.state.templates

        if latest.status == "completed":
            sections = (
                session.query(BriefingSection)
                .filter(BriefingSection.briefing_id == latest.id)
                .all()
            )
            return templates.TemplateResponse(
                request=request,
                name="partials/briefing_content.html",
                context={"briefing": latest, "sections": sections},
            )

        return templates.TemplateResponse(
            request=request,
            name="partials/generation_status.html",
            context={"status": latest.status},
        )
    finally:
        session.close()


@router.get("/api/briefings/latest")
async def latest_briefing_json():
    session = get_session()
    try:
        briefing = (
            session.query(Briefing)
            .filter(Briefing.status.in_(["completed", "partial"]))
            .order_by(Briefing.generated_at.desc())
            .first()
        )
        if not briefing:
            return {"briefing": None}

        sections = (
            session.query(BriefingSection)
            .filter(BriefingSection.briefing_id == briefing.id)
            .all()
        )
        return {
            "briefing": {
                "id": briefing.id,
                "generated_at": briefing.generated_at.isoformat(),
                "market_date": briefing.market_date.isoformat(),
                "status": briefing.status,
            },
            "sections": [
                {
                    "section_type": s.section_type,
                    "ticker": s.ticker,
                    "content": json.loads(s.content_json),
                }
                for s in sections
            ],
        }
    finally:
        session.close()
