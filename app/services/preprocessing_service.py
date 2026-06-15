from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from app.database.repositories import PostRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
AFFILIATE_PATTERN = re.compile(r"\b(affiliate|ref=|utm_source|amzn\.to|bit\.ly|tinyurl\.com|grbn\.in|flip\.in)\b", re.IGNORECASE)
INVALID_YEAR_THRESHOLD = 2000


def _normalize_text(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").strip())


def _normalize_reactions(reactions: Any) -> list[dict[str, int]] | None:
    if not reactions:
        return None
    if isinstance(reactions, str):
        try:
            reactions = json.loads(reactions)
        except json.JSONDecodeError:
            return None
    if isinstance(reactions, list):
        normalized = []
        for reaction in reactions:
            if not isinstance(reaction, dict):
                continue
            emoji = reaction.get("emoji") or reaction.get("reaction")
            count = reaction.get("count")
            try:
                count = int(count or 0)
            except (ValueError, TypeError):
                count = 0
            normalized.append({"emoji": emoji, "count": count})
        return normalized if normalized else None
    return None


def _extract_link(message: str) -> str | None:
    match = URL_PATTERN.search(message or "")
    return match.group(0) if match else None


def _is_affiliate(message: str) -> bool:
    return bool(AFFILIATE_PATTERN.search(message or ""))


def _normalize_media_type(media_type: str, message_text: str) -> str:
    if not media_type:
        media_type = "TEXT"
    media_type = media_type.upper().strip()
    if media_type in {"PHOTO", "IMAGE"}:
        return "image"
    if media_type == "VIDEO":
        return "video"
    if media_type == "POLL":
        return "poll"
    if media_type == "DOCUMENT":
        return "document"
    if media_type == "LINK" or _extract_link(message_text):
        return "link"
    if media_type == "TEXT":
        return "text"
    return "other"


def _normalize_timestamp(timestamp: Any) -> datetime | None:
    if timestamp is None:
        return None
    if isinstance(timestamp, datetime):
        ts = timestamp
    else:
        try:
            ts = datetime.fromisoformat(str(timestamp))
        except Exception:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if ts.year < INVALID_YEAR_THRESHOLD:
        return None
    now = datetime.now(timezone.utc)
    if ts > now + timedelta(days=1):
        return None
    return ts


class PreprocessingService:
    def __init__(self, session):
        self.session = session
        self.post_repo = PostRepository(session)

    async def clean_channel_posts(self, channel_id: int) -> None:
        posts = await self.post_repo.get_by_channel(channel_id)
        if not posts:
            logger.info("No posts to preprocess for channel %s", channel_id)
            return

        duplicate_groups: dict[tuple[str, datetime | None], list] = defaultdict(list)
        for post in posts:
            normalized_text = _normalize_text(post.message or "")
            duplicate_groups[(normalized_text, post.timestamp)].append(post)

        deleted_count = 0
        for group in duplicate_groups.values():
            if len(group) > 1:
                for duplicate in group[1:]:
                    await self.post_repo.delete_post(duplicate)
                    deleted_count += 1

        updated = 0
        for post in posts:
            timestamp = _normalize_timestamp(post.timestamp)
            if timestamp is None:
                await self.post_repo.delete_post(post)
                deleted_count += 1
                continue

            message_text = _normalize_text(post.message or "")
            reactions = _normalize_reactions(post.reactions)
            has_link = bool(_extract_link(message_text))
            link_url = _extract_link(message_text)
            is_affiliate = _is_affiliate(message_text)
            media_type = _normalize_media_type(post.media_type, message_text)

            values = {
                "message": message_text,
                "timestamp": timestamp,
                "views": int(post.views or 0),
                "forwards": int(post.forwards or 0),
                "reply_count": int(post.reply_count or 0),
                "reactions": reactions,
                "media_type": media_type,
                "has_link": has_link,
                "link_url": link_url,
                "is_affiliate": is_affiliate,
            }

            await self.post_repo.update_post(post, values)
            updated += 1

        logger.info(
            "Preprocessed %d posts and removed %d invalid/duplicate records for channel %s",
            updated,
            deleted_count,
            channel_id,
        )
