"""Lightweight, high-frequency subscriber polling (near-real-time).

A cheap subscriber-count sample (one Telegram call/channel) taken every ~20 min,
so growth/churn and the dashboard count stay fresh without the heavy daily
analytics snapshot. Samples accumulate in subscriber_readings.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import ChannelDNA, SubscriberReading


async def record_subscriber_reading(channel_id: str | uuid.UUID, count: int | None) -> None:
    """Store a subscriber sample and keep the channel's DNA count fresh (the
    dashboard KPI + strategy inputs read DNA.subscriber_count)."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as s:
        s.add(SubscriberReading(channel_id=cid, subscriber_count=count))
        if count is not None:
            dna = (await s.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))).scalar_one_or_none()
            if dna:
                dna.subscriber_count = count
        await s.commit()


async def get_subscriber_realtime(channel_id: str | uuid.UUID) -> dict[str, Any]:
    """Latest sampled count + change over ~the last 24h (or since the first
    sample), computed from the high-frequency readings."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                select(SubscriberReading)
                .where(SubscriberReading.channel_id == cid)
                .order_by(SubscriberReading.created_at.desc()).limit(300)
            )
        ).scalars().all()
    if not rows:
        return {"subscriber_count": None, "delta": None, "delta_pct": None,
                "window_hours": None, "samples": 0, "updated_at": None}
    latest = rows[0]
    count = latest.subscriber_count
    cutoff = latest.created_at - timedelta(hours=24)
    baseline = next((r for r in rows if r.created_at <= cutoff), rows[-1])  # ~24h ago, else oldest
    delta = delta_pct = None
    if count is not None and baseline.subscriber_count:
        delta = count - baseline.subscriber_count
        delta_pct = round(delta / baseline.subscriber_count * 100, 3)
    return {
        "subscriber_count": count,
        "delta": delta,
        "delta_pct": delta_pct,
        "window_hours": round((latest.created_at - baseline.created_at).total_seconds() / 3600, 1),
        "samples": len(rows),
        "updated_at": latest.created_at.isoformat(),
    }
