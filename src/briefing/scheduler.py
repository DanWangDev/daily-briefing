from __future__ import annotations

import asyncio
import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from briefing.config import AppConfig

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler(config: AppConfig) -> None:
    """Start the background scheduler for daily briefing generation."""
    global _scheduler

    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler()

    hour, minute = config.schedule.delivery_time.split(":")
    trigger = CronTrigger(
        hour=int(hour),
        minute=int(minute),
        timezone=config.schedule.timezone,
    )

    _scheduler.add_job(
        _run_scheduled_briefing,
        trigger=trigger,
        args=[config],
        id="daily_briefing",
        replace_existing=True,
    )

    # Background news collection — free sources every 2 hours
    _scheduler.add_job(
        _run_news_collection,
        trigger=IntervalTrigger(hours=2),
        args=[config],
        id="news_collection",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: briefing at %s %s, news collection every 2h",
        config.schedule.delivery_time,
        config.schedule.timezone,
    )


def reschedule(config: AppConfig) -> None:
    """Update the schedule with new settings."""
    global _scheduler

    if _scheduler is None:
        start_scheduler(config)
        return

    hour, minute = config.schedule.delivery_time.split(":")
    trigger = CronTrigger(
        hour=int(hour),
        minute=int(minute),
        timezone=config.schedule.timezone,
    )

    _scheduler.reschedule_job("daily_briefing", trigger=trigger)
    logger.info(
        "Rescheduled: briefing at %s %s",
        config.schedule.delivery_time,
        config.schedule.timezone,
    )


def _run_news_collection(config: AppConfig) -> None:
    """Collect news from free sources and cache in DB (called every 2h)."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_collection_job(config))
    finally:
        loop.close()


async def _async_collection_job(config: AppConfig) -> None:
    """Run free collectors and store articles."""
    from briefing.collectors.googlenews import GoogleNewsCollector
    from briefing.collectors.rss import FinancialRSSCollector
    from briefing.collectors.yahoo import YahooFinanceCollector
    from briefing.database import get_session
    from briefing.models import Holding
    from briefing.pipeline.article_store import store_articles

    session = get_session()
    try:
        holdings = session.query(Holding).all()
        if not holdings:
            return
        tickers = [h.ticker for h in holdings]
        ticker_names = {h.ticker: h.name for h in holdings}
    finally:
        session.close()

    logger.info("News collection sweep: %d tickers", len(tickers))

    collectors = [
        GoogleNewsCollector(ticker_names=ticker_names),
        FinancialRSSCollector(ticker_names=ticker_names),
        YahooFinanceCollector(),
    ]

    import asyncio as aio
    tasks = [c.collect(tickers) for c in collectors]
    results = await aio.gather(*tasks, return_exceptions=True)

    valid = []
    for collector, result in zip(collectors, results):
        if isinstance(result, Exception):
            logger.warning("Collection sweep: %s failed: %s", collector.name(), result)
        else:
            valid.append(result)

    new_count = store_articles(valid)
    logger.info("News collection sweep: %d new articles stored", new_count)


def _run_scheduled_briefing(config: AppConfig) -> None:
    """Run the briefing pipeline (called by scheduler in background thread)."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_briefing_job(config))
    finally:
        loop.close()


async def _async_briefing_job(config: AppConfig) -> None:
    """Async wrapper for the scheduled briefing."""
    from briefing.pipeline.orchestrator import run_briefing

    logger.info("Scheduled briefing starting...")
    try:
        briefing_id = await run_briefing(config)
        logger.info("Scheduled briefing #%d completed", briefing_id)

        # Send email if enabled
        if config.schedule.email_enabled:
            from briefing.database import get_session
            from briefing.delivery.email import send_briefing_email
            from briefing.models import Briefing

            session = get_session()
            try:
                briefing = session.query(Briefing).filter(Briefing.id == briefing_id).first()
                if briefing and briefing.summary_html:
                    await send_briefing_email(
                        config.email,
                        subject=f"Daily Briefing - {date.today().strftime('%B %d, %Y')}",
                        html_body=briefing.summary_html,
                    )
            finally:
                session.close()

    except Exception as e:
        logger.error("Scheduled briefing failed: %s", e)
