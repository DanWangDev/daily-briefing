from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from briefing.database import get_session
from briefing.models import Briefing, BriefingSection

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/newsmap", response_class=HTMLResponse)
async def newsmap_page(request: Request):
    session = get_session()
    try:
        latest = (
            session.query(Briefing)
            .filter(Briefing.status.in_(["completed", "partial"]))
            .order_by(Briefing.generated_at.desc())
            .first()
        )

        sections = []
        if latest:
            sections = (
                session.query(BriefingSection)
                .filter(BriefingSection.briefing_id == latest.id)
                .all()
            )

        templates = request.app.state.templates
        return templates.TemplateResponse(
            request=request,
            name="newsmap.html",
            context={
                "briefing": latest,
                "sections": sections,
            },
        )
    finally:
        session.close()
