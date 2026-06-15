import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel, Message, MessageMediaPhoto, MessageMediaDocument, MessageMediaPoll, MessageMediaWebPage

from app.config.settings import settings
from app.utils.exceptions import DataFetchError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _classify_media(message: Message) -> str:
    if not message.media:
        return "TEXT"
    if isinstance(message.media, MessageMediaPhoto):
        return "PHOTO"
    if isinstance(message.media, MessageMediaDocument):
        mime = (getattr(message.media.document, "mime_type", "") or "")
        return "VIDEO" if mime.startswith("video/") else "DOCUMENT"
    if isinstance(message.media, MessageMediaPoll):
        return "POLL"
    if isinstance(message.media, MessageMediaWebPage):
        return "TEXT"
    return "UNKNOWN"


def _extract_reactions(message: Message) -> list[dict] | None:
    if not message.reactions:
        return None
    try:
        return [
            {
                "emoji": r.reaction.emoticon if hasattr(r.reaction, "emoticon") else str(r.reaction),
                "count": r.count,
            }
            for r in message.reactions.results
        ]
    except Exception:
        return None


async def fetch_posts(client: TelegramClient, entity: Channel) -> list[dict[str, Any]]:
    limit = settings.POST_LIMIT
    logger.info("Fetching last %d posts from %s", limit, entity.title)

    posts: list[dict[str, Any]] = []
    batch: list[dict[str, Any]] = []

    try:
        async for msg in client.iter_messages(entity, limit=limit):
            data = {
                "post_id": msg.id,
                "channel_id": entity.id,
                "message": msg.text or "",
                "timestamp": msg.date,
                "views": getattr(msg, "views", 0) or 0,
                "reactions": _extract_reactions(msg),
                "forwards": getattr(msg, "forwards", 0) or 0,
                "reply_count": 0,
                "media_type": _classify_media(msg),
            }
            batch.append(data)
            if len(batch) >= 100:
                posts.extend(batch)
                logger.info("Fetched %d/%d posts", len(posts), limit)
                batch = []
                await asyncio.sleep(0.3)

        if batch:
            posts.extend(batch)
        logger.info("Post fetch complete: %d posts", len(posts))

    except FloodWaitError as e:
        logger.warning("FloodWait: sleeping %d seconds", e.seconds)
        await asyncio.sleep(e.seconds)
        return await fetch_posts(client, entity)
    except Exception as e:
        raise DataFetchError(f"Failed to fetch posts: {e}")

    return posts
