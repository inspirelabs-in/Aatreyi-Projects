import argparse
import asyncio
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.config.settings import settings
from app.database.session import async_session_factory, engine
from app.database.models import Base
from app.scheduler.cron_jobs import collect_all_channels
from app.services.channel_service import ChannelService
from app.services.storage_service import StorageService
from app.telegram.auth import authenticate
from app.telegram.client import get_telegram_client
from app.utils.exceptions import AuthenticationError, ChannelNotFoundError, DataFetchError, DatabaseError, PermissionDeniedError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def init_database() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # add new columns to existing metric tables if they are missing
        await conn.execute(text(
            "ALTER TABLE IF EXISTS content_metrics "
            "ADD COLUMN IF NOT EXISTS posting_consistency FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS posting_gaps JSON, "
            "ADD COLUMN IF NOT EXISTS content_mix JSON"
        ))
        await conn.execute(text(
            "ALTER TABLE IF EXISTS content_metrics "
            "ADD COLUMN IF NOT EXISTS avg_reach_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS median_reach_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS top_reach_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS bottom_reach_rate FLOAT DEFAULT 0.0"
        ))
        await conn.execute(text(
            "ALTER TABLE IF EXISTS performance_metrics "
            "ADD COLUMN IF NOT EXISTS average_views FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS average_reactions FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS average_forwards FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS average_replies FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS top_posts JSON, "
            "ADD COLUMN IF NOT EXISTS bottom_posts JSON"
        ))
        await conn.execute(text(
            "ALTER TABLE IF EXISTS growth_metrics "
            "ADD COLUMN IF NOT EXISTS daily_growth INTEGER DEFAULT 0, "
            "ADD COLUMN IF NOT EXISTS weekly_growth INTEGER DEFAULT 0, "
            "ADD COLUMN IF NOT EXISTS growth_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS growth_7_day FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS growth_30_day FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS growth_trend FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS trend_points JSON"
        ))
        await conn.execute(text(
            "ALTER TABLE IF EXISTS channel_features "
            "ADD COLUMN IF NOT EXISTS posts_per_day FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS avg_views FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS avg_reach_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS avg_er FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS avg_err FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS growth_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS content_mix JSON, "
            "ADD COLUMN IF NOT EXISTS top_er_posts JSON, "
            "ADD COLUMN IF NOT EXISTS top_err_posts JSON"
        ))
        # columns added by the metrics audit
        await conn.execute(text(
            "ALTER TABLE IF EXISTS content_metrics "
            "ADD COLUMN IF NOT EXISTS total_posts INTEGER DEFAULT 0"
        ))
        await conn.execute(text(
            "ALTER TABLE IF EXISTS performance_metrics "
            "ADD COLUMN IF NOT EXISTS reaction_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS forward_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS reply_rate FLOAT DEFAULT 0.0, "
            "ADD COLUMN IF NOT EXISTS engagement_rate FLOAT DEFAULT 0.0"
        ))
        # convert metrics tables to daily time-series snapshots: add snapshot_date,
        # backfill it from calculated_at, drop duplicate (channel, day) rows keeping
        # the most recent, then enforce one snapshot per channel per day. All steps
        # are idempotent so this is safe to run on every startup.
        for tbl in ("content_metrics", "performance_metrics", "growth_metrics", "channel_features"):
            await conn.execute(text(f"ALTER TABLE IF EXISTS {tbl} ADD COLUMN IF NOT EXISTS snapshot_date DATE"))
            await conn.execute(text(f"UPDATE {tbl} SET snapshot_date = calculated_at::date WHERE snapshot_date IS NULL"))
            await conn.execute(text(f"ALTER TABLE {tbl} ALTER COLUMN snapshot_date SET DEFAULT CURRENT_DATE"))
            await conn.execute(text(
                f"DELETE FROM {tbl} a USING {tbl} b "
                f"WHERE a.channel_id = b.channel_id AND a.snapshot_date = b.snapshot_date "
                f"AND (a.calculated_at < b.calculated_at "
                f"OR (a.calculated_at = b.calculated_at AND a.id < b.id))"
            ))
            await conn.execute(text(f"ALTER TABLE {tbl} ALTER COLUMN snapshot_date SET NOT NULL"))
            await conn.execute(text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{tbl}_channel_snapshot "
                f"ON {tbl} (channel_id, snapshot_date)"
            ))
    logger.info("Database tables created / verified")


async def run_once(channel: str) -> None:
    await init_database()
    client = await get_telegram_client()
    try:
        client = await authenticate(client)
        service = ChannelService(client)
        await service.collect(channel)
    except AuthenticationError as e:
        logger.error("Authentication failed: %s", e)
        sys.exit(1)
    except (ChannelNotFoundError, PermissionDeniedError) as e:
        logger.error("Channel error: %s", e)
        sys.exit(1)
    except DataFetchError as e:
        logger.error("Data fetch error: %s", e)
        sys.exit(1)
    except DatabaseError as e:
        logger.error("Database error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)
    finally:
        await client.disconnect()


async def run_all() -> None:
    await init_database()
    client = await get_telegram_client()
    try:
        client = await authenticate(client)
        service = ChannelService(client)

        async with async_session_factory() as session:
            storage = StorageService(session)
            channels = await storage.get_active_channels()

        if not channels:
            logger.warning("No active channels found. Add one via --add-channel")
            return

        for tc in channels:
            try:
                await service.collect(tc.username)
            except Exception as e:
                logger.error("Failed to collect %s: %s", tc.username, e)

    except AuthenticationError as e:
        logger.error("Authentication failed: %s", e)
        sys.exit(1)
    finally:
        await client.disconnect()


async def run_scheduler() -> None:
    await init_database()

    scheduler = AsyncIOScheduler()
    interval_hours = settings.COLLECTION_INTERVAL_HOURS

    scheduler.add_job(
        collect_all_channels,
        "interval",
        hours=interval_hours,
        id="collect_channels",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started — collecting every %d hours", interval_hours)
    logger.info("Press Ctrl+C to stop")

    try:
        await collect_all_channels()
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down scheduler")
        scheduler.shutdown()


async def add_channel(username: str) -> None:
    if not username.startswith("@"):
        username = "@" + username
    async with async_session_factory() as session:
        storage = StorageService(session)
        try:
            await storage.tracked_repo.add(username)
            logger.info("Channel %s added to tracking", username)
        except DatabaseError as e:
            logger.error("%s", e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram Growth & Retention Agent")
    parser.add_argument("--channel", "-c", help="Single channel to collect (e.g., @grabonindia)")
    parser.add_argument("--all", "-a", action="store_true", help="Collect all active tracked channels")
    parser.add_argument("--schedule", "-s", action="store_true", help="Run scheduler mode (recurring collection)")
    parser.add_argument("--add-channel", help="Add a channel to tracked list (e.g., @grabonindia)")
    parser.add_argument("--init-db", action="store_true", help="Create database tables and exit")

    args = parser.parse_args()

    if args.init_db:
        asyncio.run(init_database())
        return

    if args.add_channel:
        asyncio.run(add_channel(args.add_channel))
        return

    if args.channel:
        asyncio.run(run_once(args.channel))
        return

    if args.all:
        asyncio.run(run_all())
        return

    if args.schedule:
        asyncio.run(run_scheduler())
        return

    parser.print_help()


if __name__ == "__main__":
    main()
