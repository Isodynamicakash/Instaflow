"""
APScheduler setup — attaches to FastAPI lifespan.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.scheduler.jobs import (
    refresh_all_metrics,
    refresh_intelligence,
    update_posting_analytics,
    weekly_digest,
)

scheduler = AsyncIOScheduler()


def setup_scheduler():
    """Register all scheduled jobs."""
    # Every 6 hours: refresh post metrics (reach, saves, shares)
    scheduler.add_job(
        refresh_all_metrics,
        "interval",
        hours=6,
        id="refresh_metrics",
        replace_existing=True,
    )
    # Daily: update best posting times from historical data
    scheduler.add_job(
        update_posting_analytics,
        "cron",
        hour=2,
        id="posting_analytics",
        replace_existing=True,
    )
    # Weekly Sunday: re-run full intelligence (brand voice, themes, hashtags)
    scheduler.add_job(
        refresh_intelligence,
        "cron",
        day_of_week="sun",
        hour=3,
        id="refresh_intelligence",
        replace_existing=True,
    )
    # Weekly Monday 9am: performance digest
    scheduler.add_job(
        weekly_digest,
        "cron",
        day_of_week="mon",
        hour=9,
        id="weekly_digest",
        replace_existing=True,
    )
    return scheduler