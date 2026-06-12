import asyncio
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telethon import TelegramClient

from app.config.settings import settings
from app.database.db import AsyncSessionLocal, init_db
from app.database.repositories import (
    RegisteredChannelRepository,
    ContentMetricsRepository,
    PerformanceMetricsRepository,
)
from app.services.metadata_service import MetadataService
from app.services.metrics_service import MetricsService
from app.services.storage_service import StorageService
from app.services.subscriber_service import SubscriberService
from app.telegram.auth import authenticate
from app.telegram.client import get_telegram_client
from app.telegram.fetcher import fetch_posts
from app.telegram.resolver import resolve_channel
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def run_channel_pipeline(client: TelegramClient, channel_username: str) -> dict[str, Any]:
    logger.info("Running pipeline for %s", channel_username)

    resolved = await resolve_channel(client, channel_username)
    from telethon.tl.types import InputPeerChannel

    entity = await client.get_entity(
        InputPeerChannel(
            channel_id=resolved["channel_id"],
            access_hash=resolved["access_hash"],
        )
    )

    posts = await fetch_posts(client, entity)
    logger.info("Fetched %d posts for %s", len(posts), channel_username)

    subscriber_service = SubscriberService(client)
    subscriber_count = await subscriber_service.collect(entity)

    metadata_service = MetadataService(client)
    metadata = await metadata_service.collect(entity, resolved)

    async with AsyncSessionLocal() as session:
        storage = StorageService(session)
        registered_repo = RegisteredChannelRepository(session)
        content_repo = ContentMetricsRepository(session)
        performance_repo = PerformanceMetricsRepository(session)

        channel_data = {
            "channel_id": metadata["channel_id"],
            "title": metadata["title"],
            "username": metadata["username"],
            "description": metadata.get("description", ""),
            "created_at": metadata.get("created_at"),
            "verified": metadata.get("verified", False),
            "public_channel": metadata.get("public_channel", True),
            "subscriber_count": subscriber_count,
        }

        await storage.save_channel(channel_data)

        post_dicts = [
            {
                "message_id": p["message_id"],
                "channel_id": p["channel_id"],
                "text": p["text"],
                "media_type": p["media_type"],
                "timestamp": p["timestamp"],
                "views": p["views"],
                "forwards": p["forwards"],
                "reactions": p["reactions"],
                "reply_count": p["reply_count"],
                "has_link": p.get("has_link", False),
                "link_url": p.get("link_url"),
                "is_affiliate": p.get("is_affiliate", False),
            }
            for p in posts
        ]

        await storage.save_posts(post_dicts)
        await storage.save_snapshot(metadata["channel_id"], subscriber_count)

        content_metrics = MetricsService.calculate_content_metrics(posts, metadata["channel_id"], subscriber_count)
        performance_metrics = MetricsService.calculate_performance_metrics(posts, subscriber_count, metadata["channel_id"])

        await content_repo.save_metrics(content_metrics)
        await performance_repo.save_metrics(performance_metrics)

        await registered_repo.update_last_run_at(channel_username, datetime.utcnow())

        logger.info("Pipeline complete for %s", channel_username)

        return {
            "channel_username": channel_username,
            "channel_id": resolved["channel_id"],
            "subscriber_count": subscriber_count,
            "content_metrics": content_metrics,
            "performance_metrics": performance_metrics,
        }


async def collect_registered_channels() -> list[str]:
    async with AsyncSessionLocal() as session:
        repo = RegisteredChannelRepository(session)
        channels = await repo.get_active_channels()
        return [channel.channel_username for channel in channels]


async def run_scheduler_once() -> list[dict[str, Any]]:
    await init_db()
    client = await get_telegram_client()
    await authenticate(client)

    results: list[dict[str, Any]] = []
    try:
        registered_channels = await collect_registered_channels()
        if not registered_channels:
            logger.warning("No registered channels found for scheduler run")
            return results

        for channel_username in registered_channels:
            try:
                result = await run_channel_pipeline(client, channel_username)
                results.append(result)
            except Exception as exc:
                logger.error("Channel pipeline failed for %s: %s", channel_username, exc)

        return results
    finally:
        await client.disconnect()
        logger.info("Scheduler run complete")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)
    cron_trigger = CronTrigger.from_crontab(settings.SCHEDULER_CRON)
    scheduler.add_job(run_scheduler_once, cron_trigger, id="telegram_growth_agent_scheduler")
    return scheduler


async def start_scheduler() -> None:
    await init_db()
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started with cron: %s", settings.SCHEDULER_CRON)
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down")
        scheduler.shutdown()
