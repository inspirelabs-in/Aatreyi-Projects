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
    dispatch_due_content,
    poll_subscribers,
    publish_due_posts,
    run_daily_cycle,
    run_daily_deals,
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
    # Dedicated daily refresh for deals-aggregator channels with TODAY's deals.
    deals_hour = settings.DEAL_REFRESH_HOUR % 24
    scheduler.add_job(run_daily_deals, CronTrigger(hour=deals_hour, minute=0, timezone=LOCAL_TZ), id="daily_deals")
    # Per-slot JIT pipeline: generate each slot's post ~15-20 min before its time,
    # then publish exactly at the slot time (no more generating a whole day at once).
    scheduler.add_job(
        dispatch_due_content,
        IntervalTrigger(minutes=settings.CONTENT_DISPATCH_INTERVAL_MIN),
        id="content_dispatch",
    )
    scheduler.add_job(
        publish_due_posts,
        IntervalTrigger(minutes=settings.PUBLISH_INTERVAL_MIN),
        id="publish_due",
    )
    scheduler.add_job(
        poll_subscribers,
        IntervalTrigger(minutes=settings.SUBSCRIBER_POLL_INTERVAL_MIN),
        id="subscriber_poll",
    )
    # GrabOn deals are now slot-driven (planned by the Strategy Agent, executed by
    # dispatch_due_content per slot), so the old interval auto-poster is gone.
    return scheduler


async def main() -> None:
    _init_sentry()
    scheduler = build_scheduler()
    scheduler.start()
    # Run subscriber poll immediately on startup — don't wait for the first interval.
    # This ensures the dashboard shows a fresh reading right away, even after a restart.
    asyncio.get_event_loop().call_soon(lambda: asyncio.ensure_future(poll_subscribers()))
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
