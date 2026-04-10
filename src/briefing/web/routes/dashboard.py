from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from briefing.database import get_session
from briefing.models import Briefing, BriefingSection, Holding

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    session = get_session()
    try:
        latest = (
            session.query(Briefing)
            .filter(Briefing.status.in_(["completed", "partial"]))
            .order_by(Briefing.generated_at.desc())
            .first()
        )

        sections = []
        portfolio_snapshot = {}
        if latest:
            sections = (
                session.query(BriefingSection)
                .filter(BriefingSection.briefing_id == latest.id)
                .all()
            )
            try:
                portfolio_snapshot = json.loads(latest.portfolio_snapshot)
            except (json.JSONDecodeError, TypeError):
                portfolio_snapshot = {}

        # Count cached articles not yet in a briefing
        new_article_count = 0
        try:
            tickers = [h.ticker for h in session.query(Holding).all()]
            if tickers:
                from briefing.pipeline.article_store import count_pending_articles
                new_article_count = count_pending_articles(tickers)
        except Exception:
            pass  # non-critical — don't break dashboard

        templates = request.app.state.templates
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "briefing": latest,
                "sections": sections,
                "portfolio_snapshot": portfolio_snapshot,
                "new_article_count": new_article_count,
            },
        )
    finally:
        session.close()
