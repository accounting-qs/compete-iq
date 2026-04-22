"""APScheduler wiring for recurring GHL syncs.

Reads schedule from ghl_sync_settings (singleton row, id=1). Exposes
start/stop helpers + a reload_schedules() hook called when settings change
via PATCH /ghl-sync/settings.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from services.ghl_sync import get_sync_settings, run_sync

logger = logging.getLogger(__name__)

INCREMENTAL_JOB_ID = "ghl_incremental_sync"
WEEKLY_JOB_ID = "ghl_weekly_full_sync"

_scheduler: AsyncIOScheduler | None = None


async def _incremental_job() -> None:
    try:
        await run_sync("incremental", trigger="scheduled")
    except Exception as exc:
        logger.error("Scheduled incremental sync failed: %s", exc)


async def _weekly_job() -> None:
    try:
        await run_sync("full", trigger="scheduled")
    except Exception as exc:
        logger.error("Scheduled weekly full sync failed: %s", exc)


async def start() -> AsyncIOScheduler:
    """Start the scheduler and register jobs from current DB settings."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")
    await _apply_settings(_scheduler)
    _scheduler.start()
    logger.info("GHL scheduler started")
    return _scheduler


async def stop() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("GHL scheduler stopped")
    _scheduler = None


async def reload_schedules() -> None:
    """Re-read settings and re-register jobs. Called after settings change."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        await start()
        return
    await _apply_settings(_scheduler)
    logger.info("GHL scheduler reloaded")


async def _apply_settings(scheduler: AsyncIOScheduler) -> None:
    """Remove existing GHL jobs and re-add based on current settings."""
    for job_id in (INCREMENTAL_JOB_ID, WEEKLY_JOB_ID):
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    try:
        s = await get_sync_settings()
    except Exception as exc:
        logger.warning("Could not load sync settings (skipping schedule): %s", exc)
        return

    if s["incremental_enabled"]:
        hours = max(1, int(s["incremental_interval_hours"]))
        scheduler.add_job(
            _incremental_job,
            trigger=IntervalTrigger(hours=hours),
            id=INCREMENTAL_JOB_ID,
            max_instances=1,
            misfire_grace_time=60,
            replace_existing=True,
        )
        logger.info("Registered incremental sync every %dh", hours)

    if s["weekly_full_enabled"]:
        scheduler.add_job(
            _weekly_job,
            trigger=CronTrigger(
                day_of_week=s["weekly_full_day_of_week"],
                hour=int(s["weekly_full_hour_local"]),
                minute=0,
                timezone=s["weekly_full_timezone"],
            ),
            id=WEEKLY_JOB_ID,
            max_instances=1,
            misfire_grace_time=300,
            replace_existing=True,
        )
        logger.info(
            "Registered weekly full sync %s %02d:00 %s",
            s["weekly_full_day_of_week"], s["weekly_full_hour_local"], s["weekly_full_timezone"],
        )
