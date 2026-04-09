from __future__ import annotations

import asyncio
import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

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

    _scheduler.start()
    logger.info(
        "Scheduler started: briefing at %s %s",
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
