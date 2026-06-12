import argparse
import asyncio
import sys

from app.config.settings import settings
from app.database.db import AsyncSessionLocal, init_db
from app.database.repositories import ContentMetricsRepository, PerformanceMetricsRepository
from app.services.metadata_service import MetadataService
from app.services.metrics_service import MetricsService
from app.services.storage_service import StorageService
from app.services.subscriber_service import SubscriberService
from app.services.validation_service import ValidationService
from app.telegram.auth import authenticate
from app.telegram.client import get_telegram_client
from app.telegram.fetcher import fetch_posts
from app.telegram.resolver import resolve_channel
from app.utils.exceptions import (
    AuthenticationError,
    ChannelNotFoundError,
    DataFetchError,
    DatabaseError,
    PermissionDeniedError,
    ValidationError,
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def run_pipeline(channel_username: str):
    logger.info("=" * 50)
    logger.info("Telegram Growth & Retention Agent - Data Collection Layer")
    logger.info("=" * 50)

    client = await get_telegram_client()

    try:
        client = await authenticate(client)

        logger.info("Starting pipeline for channel: %s", channel_username)
        resolved = await resolve_channel(client, channel_username)

        # Use InputPeerChannel built from the resolved ID + access_hash
        # This avoids a second get_entity() call which can fail from cache miss
        from telethon.tl.types import InputPeerChannel
        entity = await client.get_entity(
            InputPeerChannel(
                channel_id=resolved["channel_id"],
                access_hash=resolved["access_hash"],
            )
        )

        posts = await fetch_posts(client, entity)
        logger.info("Fetched %d posts", len(posts))

        subscriber_service = SubscriberService(client)
        subscriber_count = await subscriber_service.collect(entity)
        logger.info("Subscriber count: %d", subscriber_count)

        metadata_service = MetadataService(client)
        metadata = await metadata_service.collect(entity, resolved)
        logger.info("Metadata collected")

        await init_db()

        async with AsyncSessionLocal() as session:
            storage = StorageService(session)

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
            channel = await storage.save_channel(channel_data)

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

            # Calculate and save metrics
            logger.info("Calculating metrics from posts data...")
            content_metrics = MetricsService.calculate_content_metrics(posts, metadata["channel_id"], subscriber_count)
            performance_metrics = MetricsService.calculate_performance_metrics(
                posts, subscriber_count, metadata["channel_id"]
            )

            content_repo = ContentMetricsRepository(session)
            performance_repo = PerformanceMetricsRepository(session)

            await content_repo.save_metrics(content_metrics)
            await performance_repo.save_metrics(performance_metrics)

            # Generate and log metrics summary
            summary = MetricsService.generate_summary(content_metrics, performance_metrics, subscriber_count)
            logger.info("Content Metrics: %d posts, %.2f posts/week", 
                       content_metrics["total_posts"],
                       content_metrics["posts_per_week"])
            logger.info("Performance Metrics: %.2f%% engagement rate, %.2f avg views",
                       performance_metrics["engagement_rate"],
                       content_metrics["avg_views"])

        logger.info("Data saved to database")

        validation = ValidationService()
        val_results = await validation.validate(
            channel_data=channel_data,
            subscriber_count=subscriber_count,
            posts=post_dicts,
        )

        if val_results.get("all_passed"):
            logger.info("Pipeline Completed Successfully")
        else:
            logger.warning("Pipeline completed with validation warnings")

    except AuthenticationError as e:
        logger.error("Authentication failed: %s", e)
        sys.exit(1)
    except ChannelNotFoundError as e:
        logger.error("Channel error: %s", e)
        sys.exit(1)
    except PermissionDeniedError as e:
        logger.error("Permission error: %s", e)
        sys.exit(1)
    except DataFetchError as e:
        logger.error("Data fetch error: %s", e)
        sys.exit(1)
    except DatabaseError as e:
        logger.error("Database error: %s", e)
        sys.exit(1)
    except ValidationError as e:
        logger.error("Validation error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)
    finally:
        await client.disconnect()
        logger.info("Telegram client disconnected")


def main():
    parser = argparse.ArgumentParser(
        description="Telegram Growth & Retention Agent - Data Collection Layer"
    )
    parser.add_argument(
        "--channel",
        "-c",
        required=True,
        help="Telegram channel username (e.g., @grabonindia)",
    )
    args = parser.parse_args()

    channel = args.channel.strip()
    if not channel.startswith("@"):
        channel = "@" + channel

    asyncio.run(run_pipeline(channel))


if __name__ == "__main__":
    main()
