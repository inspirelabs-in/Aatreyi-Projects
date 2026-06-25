"""APScheduler entry point — registers all cron jobs and runs forever.

    python -m scheduler.main

Times below are LOCAL to SCHEDULER_TIMEZONE (default IST); DAILY_CYCLE_HOUR sets
the morning hour for the daily cycle.
    daily   DAILY_CYCLE_HOUR:00  -> analytics + strategy (+ flagged reviews)
    weekly  Mon  (hour-1):00     -> full refresh: DNA -> competitor -> analytics -> strategy
    monthly 1st  (hour-2):00     -> full audit
    every N min                  -> content-slot dispatcher (fires ~30 min before each slot)
"""
from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings

LOCAL_TZ = ZoneInfo(settings.SCHEDULER_TIMEZONE)

from scheduler.jobs import (
    poll_subscribers,
    run_daily_cycle,
    run_monthly_audit,
    run_weekly_cycle,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scheduler.main")


def _init_sentry() -> None:
    from config import settings

    if not settings.SENTRY_DSN:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)
    except Exception:
        pass


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(
        timezone=LOCAL_TZ,
        job_defaults={"misfire_grace_time": 600, "coalesce": True, "max_instances": 1},
    )
    # Daily morning cycle: gather insights + recommend the day's strategy.
    daily_hour = settings.DAILY_CYCLE_HOUR % 24
    # Weekly/monthly run a bit earlier the same morning so the deeper refresh
    # (DNA + competitors) lands before the daily strategy build.
    weekly_hour = (daily_hour - 1) % 24
    monthly_hour = (daily_hour - 2) % 24
    scheduler.add_job(run_daily_cycle, CronTrigger(hour=daily_hour, minute=0, timezone=LOCAL_TZ), id="daily_cycle")
    scheduler.add_job(run_weekly_cycle, CronTrigger(day_of_week="mon", hour=weekly_hour, minute=0, timezone=LOCAL_TZ), id="weekly_cycle")
    scheduler.add_job(run_monthly_audit, CronTrigger(day=1, hour=monthly_hour, minute=0, timezone=LOCAL_TZ), id="monthly_audit")
    # NOTE: the per-slot content dispatcher is intentionally NOT registered —
    # content is generated in-flow right after each strategy build (onboarding +
    # daily/weekly cycles), so the Content Factory fills the moment a plan exists.
    scheduler.add_job(
        poll_subscribers,
        IntervalTrigger(minutes=settings.SUBSCRIBER_POLL_INTERVAL_MIN),
        id="subscriber_poll",
    )
    return scheduler


async def main() -> None:
    _init_sentry()
    scheduler = build_scheduler()
    scheduler.start()
    log.info("Scheduler started. Jobs:")
    for job in scheduler.get_jobs():
        log.info("  %-18s next run: %s", job.id, job.next_run_time)
    try:
        await asyncio.Event().wait()  # run forever
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down scheduler")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
