"""Shared tools used by more than one agent.

- get_telegram_channel_info(client, username)  -> channel metadata
- get_channel_posts(client, channel, days, limit) -> normalized post list
- log_agent_run(...)  -> audit row in agent_runs (start + end of every run)

Telegram tools use Telethon (MTProto). They take an already-connected client
(see tools.telegram_client.telethon_session). log_agent_run uses the async DB.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import (
    Channel as TLChannel,
    Message,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
)

from db.base import AsyncSessionLocal
from db.models import AgentRun


# ── Telegram metadata ────────────────────────────────────────────────────────
async def get_telegram_channel_info(client, username: str) -> dict[str, Any]:
    """Resolve a channel username to metadata via Telethon.

    Returns: channel_id, title, description, username, member_count, created_at.
    """
    username = username.lstrip("@")
    entity = await client.get_entity(username)
    full = await client(GetFullChannelRequest(entity))
    return {
        "channel_id": entity.id,
        "title": getattr(entity, "title", None),
        "description": getattr(full.full_chat, "about", None),
        "username": getattr(entity, "username", username),
        "member_count": getattr(full.full_chat, "participants_count", None),
        "created_at": getattr(entity, "date", None),
        "has_disappearing_messages": bool(getattr(full.full_chat, "ttl_period", None)),
    }


def _detect_format(msg: Message) -> str:
    """Map a Telethon message to one of: poll, photo, video, link, document, text."""
    if getattr(msg, "poll", None):
        return "poll"
    media = msg.media
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        mime = getattr(doc, "mime_type", "") or ""
        if mime.startswith("video"):
            return "video"
        return "document"
    if isinstance(media, MessageMediaWebPage):
        return "link"
    return "text"


def _link_preview_text(msg: Message) -> str:
    """Title + description of a message's link preview (web page card).

    Telegram resolves shared links (YouTube, articles…) into a preview card that
    carries the real title/description — e.g. a bare `youtu.be/…` post's card
    holds the video title ("… Official Trailer"). We surface that text so topic /
    category classification works on the actual subject, not an opaque URL.
    """
    media = getattr(msg, "media", None)
    wp = getattr(media, "webpage", None) if media else None
    if wp is None:
        return ""
    parts = [getattr(wp, "title", None), getattr(wp, "description", None)]
    return " — ".join(p for p in parts if p)


def _count_reactions(msg: Message) -> int:
    reactions = getattr(msg, "reactions", None)
    if not reactions or not getattr(reactions, "results", None):
        return 0
    return sum(r.count for r in reactions.results)


async def get_channel_posts(
    client, channel: str | int, days: int = 90, limit: int = 500
) -> dict[str, Any]:
    """Fetch recent posts with engagement signals via Telethon.

    `channel` may be a username (str) or a resolved channel id/entity.
    Returns {"posts": [...], "total_fetched": n}. Each post:
        message_id, text, format, views, forwards, reactions, replies, posted_at
    """
    if isinstance(channel, str):
        channel = channel.lstrip("@")
    entity = await client.get_entity(channel)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    posts: list[dict[str, Any]] = []
    async for msg in client.iter_messages(entity, limit=limit):
        if msg.date and msg.date < cutoff:
            break
        replies = getattr(msg, "replies", None)
        text = msg.message or ""
        # A bare/short link post (e.g. just a YouTube URL) carries its real
        # subject in the preview card — fold the card's title/description in so
        # classification sees "… Official Trailer", not an opaque youtu.be id.
        if len(text) < 60:
            preview = _link_preview_text(msg)
            if preview and preview.lower() not in text.lower():
                text = f"{text} {preview}".strip()
        posts.append(
            {
                "message_id": msg.id,
                "text": text,
                "format": _detect_format(msg),
                "views": msg.views or 0,
                "forwards": msg.forwards or 0,
                "reactions": _count_reactions(msg),
                "replies": getattr(replies, "replies", 0) if replies else 0,
                "posted_at": msg.date,
            }
        )
    return {"posts": posts, "total_fetched": len(posts)}


# ── Audit logging ────────────────────────────────────────────────────────────
async def log_agent_run(
    *,
    channel_id: uuid.UUID | str | None,
    agent: str,
    trigger: str,
    status: str,
    run_id: uuid.UUID | str,
    input_snapshot: dict | None = None,
    output_summary: dict | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Insert (status='running') or update (completed/failed) an agent_runs row.

    `run_id` is generated at run start and passed to both calls so the same row
    is updated on completion.
    """
    run_uuid = uuid.UUID(str(run_id))
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_uuid))
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                AgentRun(
                    id=run_uuid,
                    channel_id=uuid.UUID(str(channel_id)) if channel_id else None,
                    agent=agent,
                    trigger=trigger,
                    status=status,
                    input_snapshot=input_snapshot,
                    output_summary=output_summary,
                    duration_ms=duration_ms,
                    error=error,
                )
            )
        else:
            existing.status = status
            if output_summary is not None:
                existing.output_summary = output_summary
            if duration_ms is not None:
                existing.duration_ms = duration_ms
            if error is not None:
                existing.error = error
            if status in ("completed", "failed"):
                existing.finished_at = datetime.now(timezone.utc)
        await session.commit()
    return {"logged": True, "run_id": str(run_uuid)}
