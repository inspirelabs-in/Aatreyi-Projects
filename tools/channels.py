"""Channel record helpers shared across agents."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, ChannelDNA, Strategy, StrategyStatus


async def get_or_create_channel(username: str, **defaults: Any) -> dict[str, Any]:
    """Find a channel row by telegram_username (create a minimal one if missing).

    Returns {id, telegram_username, tier, status, ...} as a plain dict.
    """
    username = username.lstrip("@")
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(Channel).where(Channel.telegram_username == username)
            )
        ).scalar_one_or_none()
        if row is None:
            # Every channel must belong to an organization; default to GrabOn when
            # the caller didn't specify one (keeps internal/seed callers working).
            if not defaults.get("organization_id"):
                from db.models import Organization
                org_id = (await session.execute(
                    select(Organization.id).where(Organization.slug == "grabon")
                )).scalar_one_or_none()
                if org_id is not None:
                    defaults["organization_id"] = org_id
            row = Channel(telegram_username=username, **defaults)
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return {
            "id": str(row.id),
            "telegram_username": row.telegram_username,
            "tier": row.tier.value if row.tier else None,
            "status": row.status.value if row.status else None,
            "category": row.category,
        }


async def list_channels(active_only: bool = False) -> list[dict[str, Any]]:
    """All channels (for scheduler fan-out). Each: id, username, tier, status, needs_strategy_review."""
    from db.models import ChannelStatus

    async with AsyncSessionLocal() as session:
        q = select(Channel)
        if active_only:
            q = q.where(Channel.status == ChannelStatus.active)
        rows = (await session.execute(q)).scalars().all()
        return [
            {
                "id": str(r.id),
                "telegram_username": r.telegram_username,
                "tier": r.tier.value if r.tier else None,
                "status": r.status.value if r.status else None,
                "category": r.category,
                "needs_strategy_review": r.needs_strategy_review,
            }
            for r in rows
        ]


async def has_valid_dna(channel_id: str | uuid.UUID) -> bool:
    """True if a DNA profile exists with sufficient data (not the partial gate)."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        row = (await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))).scalar_one_or_none()
        return bool(row and not row.insufficient_data)


async def clear_strategy_review_flag(channel_id: str | uuid.UUID) -> None:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        row = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()
        if row:
            row.needs_strategy_review = False
            row.strategy_review_reason = None
            await session.commit()


async def get_channel_context(channel_id: str | uuid.UUID) -> dict[str, Any]:
    """Load category, sub_category, primary_topics, username for query building.

    primary_topics come from the active strategy if one exists, else fall back
    to the channel's category/sub_category.
    """
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        channel = (
            await session.execute(select(Channel).where(Channel.id == cid))
        ).scalar_one_or_none()
        if channel is None:
            return {}
        dna = (
            await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))
        ).scalar_one_or_none()
        strat = (
            await session.execute(
                select(Strategy)
                .where(Strategy.channel_id == cid, Strategy.status == StrategyStatus.active)
                .order_by(Strategy.created_at.desc())
            )
        ).scalars().first()

        category = channel.category or (dna.category if dna else None)
        sub_category = channel.sub_category or (dna.sub_category if dna else None)
        # prefer active-strategy topics, then DNA-mined specific topics, then category
        if strat and strat.primary_topics:
            primary_topics = list(strat.primary_topics)
        elif dna and dna.top_topics:
            primary_topics = list(dna.top_topics)
        else:
            primary_topics = [t for t in (category, sub_category) if t]
        return {
            "username": channel.telegram_username,
            "display_name": channel.display_name,
            "category": category,
            "sub_category": sub_category,
            "avg_er": dna.avg_er if dna else None,
            "subscriber_count": dna.subscriber_count if dna else None,
            "top_topics": (dna.top_topics if dna else None) or [],
            "primary_topics": primary_topics,
        }


async def update_channel_meta(channel_id: str | uuid.UUID, **fields: Any) -> None:
    """Patch arbitrary columns on a channel row (e.g. telegram_id, tier, display_name)."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(Channel).where(Channel.id == cid))
        ).scalar_one_or_none()
        if row is None:
            return
        for k, v in fields.items():
            if v is not None and hasattr(row, k):
                setattr(row, k, v)
        await session.commit()
