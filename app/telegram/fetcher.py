import asyncio
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel

from app.config.settings import settings
from app.utils.exceptions import DataFetchError
from app.utils.helpers import extract_post_data
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def fetch_posts(client: TelegramClient, entity: Channel) -> list[dict[str, Any]]:
    logger.info("Fetching Posts (limit: %d, batch: %d)", settings.POST_FETCH_LIMIT, settings.POST_FETCH_BATCH_SIZE)
    posts: list[dict[str, Any]] = []
    batch: list[dict[str, Any]] = []

    try:
        async for message in client.iter_messages(
            entity,
            limit=settings.POST_FETCH_LIMIT,
        ):
            post_data = extract_post_data(message, entity.id)
            batch.append(post_data)

            if len(batch) >= settings.POST_FETCH_BATCH_SIZE:
                posts.extend(batch)
                logger.info("%d/%d posts fetched", len(posts), settings.POST_FETCH_LIMIT)
                batch = []
                await asyncio.sleep(0.5)

        if batch:
            posts.extend(batch)
            logger.info("%d/%d posts fetched", len(posts), settings.POST_FETCH_LIMIT)

    except FloodWaitError as e:
        logger.warning("FloodWaitError: waiting %d seconds", e.seconds)
        await asyncio.sleep(e.seconds)
        return await fetch_posts(client, entity)

    except Exception as e:
        raise DataFetchError(f"Failed to fetch posts: {e}")

    logger.info("Post fetching complete: %d posts retrieved", len(posts))
    return posts


async def fetch_subscriber_count(client: TelegramClient, entity: Channel) -> int:
    logger.info("Fetching Subscriber Count")
    try:
        full_entity = await client.get_entity(entity)
        participants = await client.get_participants(full_entity, limit=0)
        subscribers = getattr(full_entity, "participants_count", None)
        if subscribers is None:
            subscribers = participants.total if hasattr(participants, "total") else 0
        if not subscribers:
            subscribers = len([p async for p in client.iter_participants(entity, limit=0)])
        logger.info("Subscriber Count: %d", subscribers)
        return subscribers
    except FloodWaitError as e:
        logger.warning("FloodWaitError on subscriber fetch: waiting %d seconds", e.seconds)
        await asyncio.sleep(e.seconds)
        return await fetch_subscriber_count(client, entity)
    except Exception as e:
        raise DataFetchError(f"Failed to fetch subscriber count: {e}")


async def fetch_channel_metadata(client: TelegramClient, entity: Channel, resolved: dict) -> dict[str, Any]:
    logger.info("Fetching Channel Metadata")
    try:
        full_entity = await client.get_entity(entity)
        return {
            "channel_id": entity.id,
            "title": getattr(entity, "title", ""),
            "username": getattr(entity, "username", resolved.get("username", "")),
            "description": getattr(full_entity, "about", "") if hasattr(full_entity, "about") else "",
            "created_at": getattr(entity, "date", None),
            "verified": getattr(entity, "verified", False),
            "public_channel": not getattr(entity, "username", None) is None,
        }
    except Exception as e:
        raise DataFetchError(f"Failed to fetch channel metadata: {e}")
