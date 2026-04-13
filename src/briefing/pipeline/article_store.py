"""Article cache — stores collected news incrementally and serves them at briefing time."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from briefing.database import get_session
from briefing.models import NewsArticle
from briefing.schemas import CollectorResult, NewsItem

logger = logging.getLogger(__name__)


def store_articles(results: list[CollectorResult]) -> int:
    """Persist NewsItems from collector results. Returns count of new articles."""
    session = get_session()
    new_count = 0
    try:
        for result in results:
            for item in result.news:
                if not item.url:
                    continue
                try:
                    article = NewsArticle(
                        ticker=item.related_tickers[0] if item.related_tickers else None,
                        related_tickers=json.dumps(item.related_tickers),
                        source=item.source,
                        title=item.title,
                        url=item.url,
                        published_at=item.published_at,
                        original_summary=item.snippet,
                    )
                    session.add(article)
                    session.flush()
                    new_count += 1
                except IntegrityError:
                    # Duplicate URL — already stored
                    session.rollback()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return new_count


def get_recent_articles(tickers: list[str], hours: int = 24) -> list[NewsItem]:
    """Query cached articles for the given tickers within the time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    session = get_session()
    try:
        # Match articles for portfolio tickers OR macro articles (no ticker)
        rows = (
            session.query(NewsArticle)
            .filter(
                NewsArticle.collected_at >= cutoff,
                or_(
                    NewsArticle.ticker.in_(tickers),
                    NewsArticle.ticker.is_(None),
                ),
            )
            .order_by(NewsArticle.published_at.desc())
            .all()
        )

        items: list[NewsItem] = []
        for row in rows:
            try:
                related = json.loads(row.related_tickers) if row.related_tickers else []
            except (json.JSONDecodeError, TypeError):
                related = [row.ticker] if row.ticker else []

            # SQLAlchemy's bare DateTime column on SQLite drops timezone info,
            # so rows come back tz-naive. Re-attach UTC (which is the project's
            # convention on write) so downstream code can safely compare these
            # against the tz-aware datetimes that live collectors produce.
            pub = row.published_at
            if pub is not None and pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)

            items.append(NewsItem(
                title=row.title,
                source=row.source,
                url=row.url,
                published_at=pub,
                snippet=row.original_summary or "",
                related_tickers=related,
            ))

        return items
    finally:
        session.close()


def link_to_briefing(briefing_id: int, article_urls: list[str]) -> None:
    """Associate cached articles with a completed briefing."""
    if not article_urls:
        return
    session = get_session()
    try:
        session.query(NewsArticle).filter(
            NewsArticle.url.in_(article_urls),
            NewsArticle.briefing_id.is_(None),
        ).update({"briefing_id": briefing_id}, synchronize_session=False)
        session.commit()
    finally:
        session.close()


def count_pending_articles(tickers: list[str], hours: int = 24) -> int:
    """Count articles not yet linked to a briefing."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    session = get_session()
    try:
        return (
            session.query(NewsArticle)
            .filter(
                NewsArticle.briefing_id.is_(None),
                NewsArticle.collected_at >= cutoff,
                or_(
                    NewsArticle.ticker.in_(tickers),
                    NewsArticle.ticker.is_(None),
                ),
            )
            .count()
        )
    finally:
        session.close()
