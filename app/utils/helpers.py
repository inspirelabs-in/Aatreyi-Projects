from typing import Any

from telethon.tl.types import (
    Message,
    MessageEntityTextUrl,
    MessageEntityUrl,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaPoll,
    MessageMediaWebPage,
)

from app.config.constants import AFFILIATE_PATTERNS, MediaType


def classify_media(message: Message) -> str:
    if not message.media:
        return MediaType.TEXT.value
    if isinstance(message.media, MessageMediaPhoto):
        return MediaType.PHOTO.value
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        mime_type = getattr(doc, "mime_type", "") or ""
        if mime_type.startswith("video/"):
            return MediaType.VIDEO.value
        return MediaType.DOCUMENT.value
    if isinstance(message.media, MessageMediaPoll):
        return MediaType.POLL.value
    if isinstance(message.media, MessageMediaWebPage):
        return MediaType.TEXT.value
    return MediaType.UNKNOWN.value


def extract_links(message: Message) -> tuple[bool, str | None, bool]:
    """
    Returns (has_link, first_url, is_affiliate).

    Scans message entities for MessageEntityUrl (plain URLs in text)
    and MessageEntityTextUrl (hyperlinked text). The first URL found
    is returned as link_url. is_affiliate is True when any URL matches
    a known affiliate domain pattern.
    """
    if not message.entities:
        return False, None, False

    urls: list[str] = []

    for entity in message.entities:
        if isinstance(entity, MessageEntityUrl):
            # Plain URL — slice it out of the message text
            start = entity.offset
            end = entity.offset + entity.length
            url = (message.text or "")[start:end]
            if url:
                urls.append(url)
        elif isinstance(entity, MessageEntityTextUrl):
            # Hyperlinked text — URL is stored directly on the entity
            if entity.url:
                urls.append(entity.url)

    if not urls:
        return False, None, False

    first_url = urls[0]
    is_affiliate = any(
        pattern in url.lower()
        for url in urls
        for pattern in AFFILIATE_PATTERNS
    )
    return True, first_url, is_affiliate


def extract_post_data(message: Message, channel_id: int) -> dict[str, Any]:
    # ── Reactions ──────────────────────────────────────────────────────────
    reactions = None
    if message.reactions:
        try:
            reactions = [
                {
                    "emoji": (
                        r.reaction.emoticon
                        if hasattr(r.reaction, "emoticon")
                        else str(r.reaction)
                    ),
                    "count": r.count,
                }
                for r in message.reactions.results
            ]
        except Exception:
            reactions = None

    # ── Reply count ────────────────────────────────────────────────────────
    # message.replies is a MessageReplies object present on channel posts.
    # .replies holds the public reply count; falls back to 0 when absent
    # (e.g. older posts, channels with comments disabled).
    reply_count = 0
    if message.replies is not None:
        reply_count = getattr(message.replies, "replies", 0) or 0

    # ── Link extraction ────────────────────────────────────────────────────
    has_link, link_url, is_affiliate = extract_links(message)

    return {
        "message_id": message.id,
        "channel_id": channel_id,
        "text": message.text or "",
        "media_type": classify_media(message),
        "timestamp": message.date,
        "views": getattr(message, "views", 0) or 0,
        "forwards": getattr(message, "forwards", 0) or 0,
        "reactions": reactions,
        "reply_count": reply_count,
        "has_link": has_link,
        "link_url": link_url,
        "is_affiliate": is_affiliate,
    }
