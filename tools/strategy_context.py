"""Strategy Context for the Content Generator.

The Content Generator must not caption using only the selected deal/source — it also
receives the Strategy Agent's context so every caption reflects the channel's DNA,
today's strategy, the slot's reason, audience, tone, competitor intelligence,
historical engagement, trending themes and preferred CTA style. Competitor
intelligence is GUIDANCE for original writing — captions are never copied.

`build_strategy_context(channel_id)` assembles the dict (one cheap set of reads,
cached briefly); `strategy_context_prompt(ctx, slot_reason)` renders it into the
prompt block appended to generation.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import (
    AnalyticsSnapshot,
    ChannelDNA,
    SnapshotType,
    Strategy,
    StrategyStatus,
)

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 300  # 5 min — strategy/DNA change slowly; avoids re-querying per slot.


async def build_strategy_context(channel_id: str | uuid.UUID) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    ck = str(cid)
    hit = _CACHE.get(ck)
    if hit and (time.time() - hit[0]) < _TTL:
        return hit[1]

    async with AsyncSessionLocal() as s:
        dna = (await s.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))).scalar_one_or_none()
        strat = (await s.execute(
            select(Strategy).where(Strategy.channel_id == cid, Strategy.status == StrategyStatus.active)
            .order_by(Strategy.created_at.desc())
        )).scalars().first()
        snap = (await s.execute(
            select(AnalyticsSnapshot).where(
                AnalyticsSnapshot.channel_id == cid, AnalyticsSnapshot.snapshot_type == SnapshotType.daily)
            .order_by(AnalyticsSnapshot.created_at.desc())
        )).scalars().first()

    analysis = (strat.analysis or {}) if strat else {}
    intel = analysis.get("competitor_intelligence") or {}
    intelligence = (getattr(snap, "intelligence", None) or {}) if snap else {}
    fe = intelligence.get("format_engagement") or []
    er_by_format = {e["label"]: e["avg_er"] for e in fe if e.get("avg_er") is not None}

    ctx: dict[str, Any] = {
        "niche": (dna.category if dna else None),
        "sub_niche": (dna.sub_category if dna else None),
        "audience": (getattr(dna, "audience_geo_top3", None) if dna else None),
        "tone": (getattr(dna, "tone_fingerprint", None) if dna else None),
        "top_topics": (dna.top_topics if dna else None) or [],
        "goal": (strat.goal if strat else None),
        "primary_topics": (strat.primary_topics if strat else None) or [],
        "trending_themes": intel.get("trending_categories") or intel.get("emerging_trends") or [],
        "preferred_cta": intel.get("best_cta") or [],
        "competitor_best_format": intel.get("best_media_mix") or intel.get("best_format"),
        "content_gaps": intel.get("content_gaps") or [],
        "historical_engagement": {
            "avg_er": (dna.avg_er if dna else None),
            "er_by_format": er_by_format,
            "best_post_hour": (dna.best_post_hour if dna else None),
        },
    }
    _CACHE[ck] = (time.time(), ctx)
    return ctx


def _fmt_list(xs, n=5) -> str:
    return ", ".join(str(x) for x in (xs or [])[:n])


def strategy_context_prompt(ctx: dict[str, Any] | None, slot_reason: str | None = None) -> str:
    """Render the strategy context into a prompt block. Empty string when no context
    (so callers can always append it safely)."""
    if not ctx:
        return ""
    he = ctx.get("historical_engagement") or {}
    lines = ["\n--- STRATEGY CONTEXT (shape the writing; do not copy competitors) ---"]
    if ctx.get("niche"):
        lines.append(f"Niche: {ctx['niche']}" + (f" / {ctx['sub_niche']}" if ctx.get("sub_niche") else ""))
    if ctx.get("audience"):
        lines.append(f"Target audience: {_fmt_list(ctx['audience'])}")
    if ctx.get("tone"):
        lines.append(f"Preferred tone: {ctx['tone']}")
    if ctx.get("goal"):
        lines.append(f"Today's strategy goal: {ctx['goal']}")
    if slot_reason:
        lines.append(f"Why this slot exists: {slot_reason}")
    if ctx.get("primary_topics"):
        lines.append(f"Focus topics: {_fmt_list(ctx['primary_topics'])}")
    if ctx.get("trending_themes"):
        lines.append(f"Trending themes (guidance): {_fmt_list(ctx['trending_themes'])}")
    if ctx.get("preferred_cta"):
        lines.append(f"CTA styles that work in this niche (adapt, don't copy): {_fmt_list(ctx['preferred_cta'])}")
    if he.get("er_by_format"):
        top = sorted(he["er_by_format"].items(), key=lambda kv: -(kv[1] or 0))[:2]
        lines.append("Highest-engagement formats historically: " + ", ".join(f"{k} ({v}%)" for k, v in top))
    lines.append(
        "Use this context to shape the HEADLINE, HOOK, CTA wording, emoji usage, urgency and formatting so the "
        "post fits this channel and audience. Competitor intelligence is GUIDANCE only — write ORIGINAL copy, "
        "never reuse a competitor's caption."
    )
    return "\n".join(lines) + "\n"
