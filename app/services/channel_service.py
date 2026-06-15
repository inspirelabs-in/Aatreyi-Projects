from typing import Any

from telethon import TelegramClient

from app.config.schemas import ChannelResolved
from app.database.session import async_session_factory
from app.services.metrics_service import MetricsService
from app.services.storage_service import StorageService
from app.services.validation_service import ValidationService
from app.services.content_metrics_service import ContentMetricsService
from app.services.engagement_service import EngagementService
from app.telegram.fetcher import fetch_posts
from app.telegram.resolver import resolve_channel
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ChannelService:
    def __init__(self, client: TelegramClient):
        self.client = client

    async def collect(self, username: str) -> dict[str, Any]:
        logger.info("=" * 50)
        logger.info("Collection started for: %s", username)
        logger.info("=" * 50)

        resolved: ChannelResolved = await resolve_channel(self.client, username)
        entity = await self.client.get_entity(username)

        posts = await fetch_posts(self.client, entity)
        logger.info("Posts collected: %d", len(posts))

        async with async_session_factory() as session:
            storage = StorageService(session)
            channel_data = {
                "channel_id": resolved.channel_id,
                "title": resolved.title,
                "username": resolved.username,
                "description": resolved.description,
                "created_at": None,
                "verified": resolved.verified,
                "public_channel": resolved.public_channel,
            }
            await storage.save_channel(channel_data)

            post_dicts = [
                {
                    "post_id": p["post_id"],
                    "channel_id": p["channel_id"],
                    "message": p["message"],
                    "timestamp": p["timestamp"],
                    "views": p["views"],
                    "reactions": p["reactions"],
                    "forwards": p["forwards"],
                    "reply_count": p["reply_count"],
                    "media_type": p["media_type"],
                    "has_link": p.get("has_link", False),
                    "link_url": p.get("link_url"),
                    "is_affiliate": p.get("is_affiliate", False),
                }
                for p in posts
            ]
            inserted = await storage.save_posts(post_dicts)

            await storage.save_snapshot(resolved.channel_id, resolved.subscriber_count)

            logger.info("Data saved to database for %s", username)

            async with async_session_factory() as metrics_session:
                metrics_service = MetricsService(metrics_session)
                await metrics_service.process_channel(
                    channel_id=resolved.channel_id,
                    subscribers=resolved.subscriber_count,
                )

            validation = ValidationService()
            result = validation.validate(
                channel_exists=True,
                subscriber_count=resolved.subscriber_count,
                posts=post_dicts,
            )

        self._print_summary(resolved, post_dicts, result)
        logger.info("Collection completed for: %s", username)
        return {"channel": resolved, "posts": len(post_dicts), "status": result}

    def _print_summary(self, resolved: ChannelResolved, posts: list, result: dict) -> None:
        SEP = "=" * 50
        print(f"\n{SEP}")
        print(f"Channel: {resolved.title}")
        print(f"Subscribers: {resolved.subscriber_count:,}")
        print(f"Posts Collected: {len(posts)}")

        timestamps = [p["timestamp"] for p in posts if p.get("timestamp")]
        if len(timestamps) >= 2:
            print(f"Date Range:")
            print(f"  {min(timestamps).strftime('%Y-%m-%d')} -> {max(timestamps).strftime('%Y-%m-%d')}")

        print(f"Status:")
        print(f"  {'ALL CHECKS PASSED' if result['all_passed'] else 'VALIDATION FAILED'}")
        print(f"{SEP}\n")
