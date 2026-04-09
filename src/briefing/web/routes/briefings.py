from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from briefing.database import get_session
from briefing.models import Briefing, BriefingSection

logger = logging.getLogger(__name__)
router = APIRouter()


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
    """Trigger a manual briefing generation."""
    from briefing.pipeline.orchestrator import run_briefing

    config = request.app.state.config
    try:
        briefing_id = await run_briefing(config)
    except Exception as e:
        logger.error("Briefing generation failed: %s", e)
        return HTMLResponse(
            f'<article style="text-align:center;padding:2rem;">'
            f'<h3>Generation failed</h3><p>{e}</p></article>'
        )

    session = get_session()
    try:
        briefing = session.query(Briefing).filter(Briefing.id == briefing_id).first()
        sections = (
            session.query(BriefingSection)
            .filter(BriefingSection.briefing_id == briefing_id)
            .all()
        ) if briefing else []

        templates = request.app.state.templates
        return templates.TemplateResponse(
            request=request,
            name="partials/briefing_content.html",
            context={"briefing": briefing, "sections": sections},
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
