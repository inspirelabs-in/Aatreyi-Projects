"""Service layer: read aggregations + manual agent runner.

Keeps routers thin and avoids async lazy-load pitfalls by building plain dicts.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.analytics import classify_churn_risk, detect_sustained_decline
from tools.subscribers import get_subscriber_realtime
from db.models import (
    AgentName,
    AgentRun,
    AnalyticsSnapshot,
    Channel,
    ChannelDNA,
    Competitor,
    GeneratedPost,
    PostQueue,
    QueueStatus,
    ReviewStatus,
    RunStatus,
    SnapshotType,
    Strategy,
    StrategyStatus,
    StrategyTask,
    SubscriberReading,
)


def _uid(v) -> uuid.UUID:
    return uuid.UUID(str(v))


async def get_channel_or_none(session: AsyncSession, channel_id: str) -> Channel | None:
    try:
        cid = _uid(channel_id)
    except ValueError:
        return None  # malformed id -> treat as not found (404, not 500)
    return (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()


async def build_dashboard(session: AsyncSession, channel_id: str) -> dict:
    cid = _uid(channel_id)
    channel = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()
    if channel is None:
        return {}
    dna = (await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))).scalar_one_or_none()
    latest_daily = (
        await session.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.channel_id == cid, AnalyticsSnapshot.snapshot_type == SnapshotType.daily)
            .order_by(AnalyticsSnapshot.created_at.desc())
        )
    ).scalars().first()
    today_tasks = (
        await session.execute(
            select(StrategyTask)
            .where(StrategyTask.channel_id == cid, StrategyTask.scheduled_date == date.today())
            .order_by(StrategyTask.scheduled_time.asc())
        )
    ).scalars().all()
    pending = (
        await session.execute(
            select(GeneratedPost).where(
                GeneratedPost.channel_id == cid, GeneratedPost.review_status == ReviewStatus.pending
            )
        )
    ).scalars().all()

    return {
        "channel": {
            "id": str(channel.id),
            "telegram_username": channel.telegram_username,
            "display_name": channel.display_name,
            "tier": channel.tier.value if channel.tier else None,
            "category": channel.category,
            "status": channel.status.value if channel.status else None,
            "needs_strategy_review": channel.needs_strategy_review,
        },
        "kpis": {
            "subscriber_count": dna.subscriber_count if dna else None,
            "avg_er": dna.avg_er if dna else None,
            "post_frequency_per_day": dna.post_frequency_per_day if dna else None,
            "best_post_hour": dna.best_post_hour if dna else None,
            "subscriber_delta": latest_daily.subscriber_delta if latest_daily else None,
            "subscriber_delta_pct": latest_daily.subscriber_delta_pct if latest_daily else None,
            "pending_review": len(pending),
        },
        "insights": (latest_daily.insights if latest_daily else None) or [],
        "timeline": [
            {
                "task_id": str(t.id),
                "time": t.scheduled_time.isoformat() if t.scheduled_time else None,
                "format": t.format.value if t.format else None,
                "topic": t.topic,
                "status": t.status.value if t.status else None,
            }
            for t in today_tasks
        ],
    }


async def get_queue(session: AsyncSession, channel_id: str) -> list[dict]:
    """Recent generated posts of ALL review states (pending/approved/edited/
    rejected) + whether each was actually published (its queue row is 'sent').
    The Content page filters these by status and date client-side."""
    cid = _uid(channel_id)
    rows = (
        await session.execute(
            select(GeneratedPost, PostQueue.scheduled_at, PostQueue.status)
            .join(PostQueue, PostQueue.generated_post_id == GeneratedPost.id, isouter=True)
            .where(GeneratedPost.channel_id == cid)
            .order_by(GeneratedPost.created_at.desc())
            .limit(300)
        )
    ).all()
    return [
        {
            "generated_post_id": str(r.id),
            "post_text": r.post_text,
            "post_format": r.post_format.value if r.post_format else None,
            "media_url": r.media_url,
            "link_url": r.link_url,
            "poll_options": r.poll_options,
            "cta": r.cta,
            "hashtags": r.hashtags,
            "review_status": r.review_status.value,
            "published": qstatus == QueueStatus.sent,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r, scheduled_at, qstatus in rows
    ]


async def get_analytics(session: AsyncSession, channel_id: str, snapshot_type: str, n: int) -> list[dict]:
    cid = _uid(channel_id)
    rows = (
        await session.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.channel_id == cid, AnalyticsSnapshot.snapshot_type == SnapshotType(snapshot_type))
            .order_by(AnalyticsSnapshot.created_at.desc())
            .limit(n)
        )
    ).scalars().all()
    rows = list(reversed(rows))  # chronological for charting
    return [
        {
            "period_end": r.period_end.isoformat() if r.period_end else None,
            "subscriber_count": r.subscriber_count,
            "subscriber_delta": r.subscriber_delta,
            "subscriber_delta_pct": r.subscriber_delta_pct,
            "avg_views": r.avg_views,
            "avg_er": r.avg_er,
            "total_posts": r.total_posts,
            "churn_signal": r.churn_signal,
            "insights": r.insights or [],
        }
        for r in rows
    ]


async def get_strategy(session: AsyncSession, channel_id: str) -> dict | None:
    cid = _uid(channel_id)
    strat = (
        await session.execute(
            select(Strategy)
            .where(Strategy.channel_id == cid, Strategy.status == StrategyStatus.active)
            .order_by(Strategy.created_at.desc())
        )
    ).scalars().first()
    if strat is None:
        return None
    tasks = (
        await session.execute(
            select(StrategyTask)
            .where(StrategyTask.strategy_id == strat.id)
            .order_by(StrategyTask.scheduled_date.asc(), StrategyTask.scheduled_time.asc())
        )
    ).scalars().all()
    return {
        "strategy_id": str(strat.id),
        "strategy_type": strat.strategy_type.value if strat.strategy_type else None,
        "goal": strat.goal,
        "post_frequency_per_day": strat.post_frequency_per_day,
        "content_mix": strat.content_mix,
        "primary_topics": strat.primary_topics,
        "growth_tactics": strat.growth_tactics,
        "diagnosis": (strat.analysis or {}).get("diagnosis"),
        "auto_applied": (strat.analysis or {}).get("auto_applied") or [],
        "strategy_profile": (strat.analysis or {}).get("strategy_profile") or None,
        "deals_plan": (strat.analysis or {}).get("deals_plan") or [],
        "benchmark": (strat.analysis or {}).get("benchmark"),
        "fatigue": (strat.analysis or {}).get("fatigue"),
        "competitor_insights": (strat.analysis or {}).get("competitor_insights") or [],
        "competitor_intelligence": (strat.analysis or {}).get("competitor_intelligence") or {},
        "growth_recommendations": (strat.analysis or {}).get("growth_recommendations") or [],
        "retention_recommendations": (strat.analysis or {}).get("retention_recommendations") or [],
        "period_start": strat.period_start.isoformat() if strat.period_start else None,
        "period_end": strat.period_end.isoformat() if strat.period_end else None,
        "tasks": [
            {
                "task_id": str(t.id),
                "date": t.scheduled_date.isoformat() if t.scheduled_date else None,
                "time": t.scheduled_time.isoformat() if t.scheduled_time else None,
                "scrape_at": t.scrape_at.isoformat() if t.scrape_at else None,
                "format": t.format.value if t.format else None,
                "topic": t.topic,
                "kind": t.kind,
                "marketplace": t.marketplace,
                "media_type": t.media_type,
                "priority": t.priority,
                "rationale": t.rationale,
                "status": t.status.value if t.status else None,
            }
            for t in tasks
        ],
    }


async def get_competitors(session: AsyncSession, channel_id: str) -> list[dict]:
    cid = _uid(channel_id)
    rows = (
        await session.execute(
            select(Competitor)
            .where(Competitor.channel_id == cid)
            .order_by(Competitor.rank.asc().nulls_last())
        )
    ).scalars().all()
    return [
        {
            "competitor_username": r.competitor_username,
            "display_name": r.display_name,
            "subscriber_count": r.subscriber_count,
            "avg_er": r.avg_er,
            "post_frequency_per_day": r.post_frequency_per_day,
            "top_content_themes": r.top_content_themes,
            "rank": r.rank,
            "rank_score": r.rank_score,
            "source": r.source.value if r.source else None,
            "has_disappearing_messages": r.has_disappearing_messages,
            "competitor_type": r.competitor_type,
            "similarity_breakdown": r.similarity_breakdown,
            "intelligence": r.intelligence,
        }
        for r in rows
    ]


async def get_agent_runs(session: AsyncSession, status: str | None, limit: int) -> list[dict]:
    """Recent agent_runs (audit log); optionally filter by status (e.g. failed)."""
    q = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
    if status:
        q = q.where(AgentRun.status == RunStatus(status))
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "channel_id": str(r.channel_id) if r.channel_id else None,
            "agent": r.agent.value if r.agent else None,
            "trigger": r.trigger.value if r.trigger else None,
            "status": r.status.value if r.status else None,
            "duration_ms": r.duration_ms,
            "error": r.error,
            "output_summary": r.output_summary,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in rows
    ]


# ── Control Room (agent-centric live state) ──────────────────────────────────
_AGENT_META: dict[str, dict] = {
    "channel_dna": {"label": "Channel DNA", "icon": "🧬",
                    "steps": ["Fetch posts", "Compute ER", "Detect niche", "Save DNA"]},
    "competitor_intelligence": {"label": "Competitor", "icon": "🕵️",
                    "steps": ["Keywords + brands", "Resolve handles", "Enrich + score", "Rank + benchmark"]},
    "analytics": {"label": "Analytics", "icon": "📊",
                    "steps": ["Fetch metrics", "Compute delta", "Detect churn", "Generate insights"]},
    "strategy": {"label": "Strategy", "icon": "🧠",
                    "steps": ["Read DNA + analytics", "Adjust plan", "Schedule slots", "Set targets"]},
    "content_intelligence": {"label": "Content", "icon": "✍️",
                    "steps": ["Ingest sources", "Score (7 signals)", "Generate post", "Queue review"]},
}
_AGENT_ORDER = ["channel_dna", "competitor_intelligence", "analytics", "strategy", "content_intelligence"]
_STATUS_MAP = {RunStatus.completed: "done", RunStatus.running: "running", RunStatus.failed: "failed"}
_ACTION_VERB = {RunStatus.completed: "completed", RunStatus.running: "is working", RunStatus.failed: "failed"}


def _compact_summary(summary) -> str:
    """A short human result line from an agent_run output_summary dict."""
    if not isinstance(summary, dict) or not summary:
        return ""
    parts = []
    for k, v in summary.items():
        if isinstance(v, (str, int, float, bool)) and v is not None and v != "":
            parts.append(f"{k}: {v}")
        if len(parts) >= 3:
            break
    return " · ".join(parts)


async def build_control_state(session: AsyncSession, channel_id: str) -> dict:
    """Agent-centric live state for the Control Room: event stream, pipeline
    status per agent, and a lightweight system snapshot — all derived from the
    agent_runs audit log + the latest DNA / analytics the agents produced."""
    cid = _uid(channel_id)
    channel = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()
    runs = (
        await session.execute(
            select(AgentRun).where(AgentRun.channel_id == cid)
            .order_by(AgentRun.started_at.desc()).limit(50)
        )
    ).scalars().all()

    # ── event stream ──
    events = []
    for r in runs:
        meta = _AGENT_META.get(r.agent.value, {"label": r.agent.value, "icon": "•"})
        events.append({
            "id": str(r.id),
            "agent": r.agent.value,
            "label": meta["label"],
            "icon": meta["icon"],
            "action": _ACTION_VERB.get(r.status, r.status.value),
            "result": _compact_summary(r.output_summary),
            "status": _STATUS_MAP.get(r.status, r.status.value),
            "ts": r.started_at.isoformat() if r.started_at else None,
            "reason": (r.error or "")[:160] if r.status == RunStatus.failed else None,
            "duration_ms": r.duration_ms,
        })

    # ── pipeline: latest run per agent ──
    latest: dict[str, AgentRun] = {}
    for r in runs:  # runs are newest-first; keep the first seen per agent
        latest.setdefault(r.agent.value, r)
    pipeline = []
    for name in _AGENT_ORDER:
        meta = _AGENT_META[name]
        r = latest.get(name)
        pipeline.append({
            "agent": name,
            "label": meta["label"],
            "icon": meta["icon"],
            "steps": meta["steps"],
            "status": _STATUS_MAP.get(r.status, "idle") if r else "idle",
            "last_run": r.started_at.isoformat() if (r and r.started_at) else None,
            "duration_ms": r.duration_ms if r else None,
            "summary": _compact_summary(r.output_summary) if r else "",
        })

    # ── system snapshot (agent-derived) ──
    dna = (await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))).scalar_one_or_none()
    recent_daily = (
        await session.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.channel_id == cid, AnalyticsSnapshot.snapshot_type == SnapshotType.daily)
            .order_by(AnalyticsSnapshot.created_at.desc()).limit(4)
        )
    ).scalars().all()
    latest_daily = recent_daily[0] if recent_daily else None

    churn = bool(latest_daily.churn_signal) if latest_daily else False
    # spike vs slow-bleed — derived from recent snapshot deltas (no extra column)
    _deltas = [s.subscriber_delta_pct for s in recent_daily]
    if _deltas and detect_sustained_decline(_deltas[0], _deltas[1:]):
        churn_type = "sustained"
    elif churn:
        churn_type = "spike"
    else:
        churn_type = None

    # Near-real-time subscribers (sampled every ~20 min) override the once-a-day
    # snapshot for the live count + growth; fall back to the daily snapshot/DNA.
    rt = await get_subscriber_realtime(channel_id)
    daily_delta_pct = latest_daily.subscriber_delta_pct if latest_daily else None
    delta_pct = rt["delta_pct"] if rt["delta_pct"] is not None else daily_delta_pct
    sub_count = rt["subscriber_count"] if rt["subscriber_count"] is not None else (dna.subscriber_count if dna else None)

    if churn or (delta_pct is not None and delta_pct < -0.05):
        retention_trend = "down"
    elif delta_pct is not None and delta_pct > 0.1:
        retention_trend = "up"
    else:
        retention_trend = "flat"

    recent = runs[:15]
    any_failed = any(r.status == RunStatus.failed for r in recent)
    latest_failed = any(r.status == RunStatus.failed for r in latest.values())
    thinking = any(r.status == RunStatus.running for r in recent)
    agent_health = "red" if latest_failed else ("yellow" if any_failed else "green")

    return {
        "channel": {
            "id": str(channel.id) if channel else channel_id,
            "telegram_username": channel.telegram_username if channel else None,
            "display_name": channel.display_name if channel else None,
            "tier": channel.tier.value if (channel and channel.tier) else None,
            "category": channel.category if channel else None,
        },
        "events": events,
        "pipeline": pipeline,
        "system": {
            "subscriber_count": sub_count,
            "growth_rate": delta_pct,
            "retention_trend": retention_trend,
            "engagement_pulse": dna.avg_er if dna else None,
            "churn_risk": classify_churn_risk(delta_pct, churn),
            "churn_type": churn_type,
            "agent_health": agent_health,
            "thinking": thinking,
            "subscribers_updated_at": rt["updated_at"],
            "subscriber_samples": rt["samples"],
        },
    }


async def get_subscriber_series(session: AsyncSession, channel_id: str, n: int = 300) -> list[dict]:
    """Real subscriber samples (every ~20 min) as a chronological series with
    per-sample delta — this is the live, updating subscriber-growth source."""
    cid = _uid(channel_id)
    rows = (
        await session.execute(
            select(SubscriberReading)
            .where(SubscriberReading.channel_id == cid)
            .order_by(SubscriberReading.created_at.desc()).limit(n)
        )
    ).scalars().all()
    rows = list(reversed(rows))  # chronological
    out = []
    prev = None
    for r in rows:
        c = r.subscriber_count
        out.append({
            "ts": r.created_at.isoformat() if r.created_at else None,
            "subscriber_count": c,
            "delta": (c - prev) if (c is not None and prev is not None) else None,
        })
        if c is not None:
            prev = c
    return out


async def get_intelligence(session: AsyncSession, channel_id: str) -> dict:
    """Latest post/audience intelligence (Phase 1) + the active retention plan
    (Phase 2 habit-loop slots) for the Control Room intelligence panel."""
    cid = _uid(channel_id)
    recent = (
        await session.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.channel_id == cid)
            .order_by(AnalyticsSnapshot.created_at.desc()).limit(40)
        )
    ).scalars().all()
    # Show the LATEST snapshot with a MEANINGFUL sample (recent is already ordered
    # created_at desc). Picking "most posts_analyzed" instead made the page stick
    # permanently on a big monthly snapshot (e.g. 500 posts) so it never changed
    # when newer daily runs produced fresher numbers. The >=10 floor skips a thin
    # partial-day window (e.g. 2 posts) so the numbers stay both fresh and useful.
    with_intel = [s for s in recent if (s.intelligence or {}).get("posts_analyzed")]
    snap = (
        next((s for s in with_intel if s.intelligence["posts_analyzed"] >= 10), None)
        or (with_intel[0] if with_intel else (recent[0] if recent else None))
    )
    intel = (snap.intelligence if snap else None) or {}
    strat = (
        await session.execute(
            select(Strategy).where(Strategy.channel_id == cid, Strategy.status == StrategyStatus.active)
            .order_by(Strategy.created_at.desc())
        )
    ).scalars().first()
    retention_slots = []
    if strat:
        rows = (
            await session.execute(
                select(StrategyTask).where(StrategyTask.strategy_id == strat.id, StrategyTask.kind.isnot(None))
                .order_by(StrategyTask.scheduled_date.asc(), StrategyTask.scheduled_time.asc())
            )
        ).scalars().all()
        retention_slots = [
            {"kind": t.kind, "format": t.format.value if t.format else None,
             "topic": t.topic, "date": t.scheduled_date.isoformat() if t.scheduled_date else None,
             "status": t.status.value if t.status else None}
            for t in rows
        ]
    return {"intelligence": intel, "retention_plan": retention_slots}


# ── Admin (global, cross-tenant) ─────────────────────────────────────────────
async def admin_overview(session: AsyncSession) -> dict:
    channels = (await session.execute(select(func.count(Channel.id)))).scalar() or 0
    runs = (await session.execute(select(func.count(AgentRun.id)))).scalar() or 0
    failed = (await session.execute(select(func.count(AgentRun.id)).where(AgentRun.status == RunStatus.failed))).scalar() or 0
    running = (await session.execute(select(func.count(AgentRun.id)).where(AgentRun.status == RunStatus.running))).scalar() or 0
    pending = (await session.execute(select(func.count(GeneratedPost.id)).where(GeneratedPost.review_status == ReviewStatus.pending))).scalar() or 0
    return {
        "channels": channels, "agent_runs": runs, "failed_runs": failed,
        "running_now": running, "pending_review": pending,
        "success_rate": round((runs - failed) / runs * 100, 1) if runs else None,
    }


async def admin_agent_performance(session: AsyncSession) -> list[dict]:
    out = []
    for name in _AGENT_ORDER:
        ae = AgentName(name)
        total = (await session.execute(select(func.count(AgentRun.id)).where(AgentRun.agent == ae))).scalar() or 0
        failed = (await session.execute(select(func.count(AgentRun.id)).where(AgentRun.agent == ae, AgentRun.status == RunStatus.failed))).scalar() or 0
        avg_ms = (await session.execute(select(func.avg(AgentRun.duration_ms)).where(AgentRun.agent == ae, AgentRun.status == RunStatus.completed))).scalar()
        meta = _AGENT_META[name]
        out.append({
            "agent": name, "label": meta["label"], "icon": meta["icon"],
            "runs": total, "failed": failed,
            "success_rate": round((total - failed) / total * 100, 1) if total else None,
            "avg_ms": round(avg_ms) if avg_ms else None,
        })
    return out


async def admin_all_channels(session: AsyncSession) -> list[dict]:
    chans = (await session.execute(select(Channel).order_by(Channel.created_at.desc()))).scalars().all()
    out = []
    for c in chans:
        dna = (await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == c.id))).scalar_one_or_none()
        last = (await session.execute(select(AgentRun).where(AgentRun.channel_id == c.id).order_by(AgentRun.started_at.desc()))).scalars().first()
        pending = (await session.execute(select(func.count(GeneratedPost.id)).where(GeneratedPost.channel_id == c.id, GeneratedPost.review_status == ReviewStatus.pending))).scalar() or 0
        out.append({
            "id": str(c.id), "telegram_username": c.telegram_username, "display_name": c.display_name,
            "tier": c.tier.value if c.tier else None, "category": c.category,
            "status": c.status.value if c.status else None,
            "subscriber_count": dna.subscriber_count if dna else None,
            "avg_er": dna.avg_er if dna else None,
            "last_agent": last.agent.value if last else None,
            "last_activity": last.started_at.isoformat() if (last and last.started_at) else None,
            "last_status": _STATUS_MAP.get(last.status, "idle") if last else None,
            "pending_review": pending,
        })
    return out


async def admin_global_events(session: AsyncSession, limit: int = 60) -> list[dict]:
    runs = (await session.execute(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit))).scalars().all()
    chans = {c.id: c for c in (await session.execute(select(Channel))).scalars().all()}
    events = []
    for r in runs:
        meta = _AGENT_META.get(r.agent.value, {"label": r.agent.value, "icon": "•"})
        c = chans.get(r.channel_id)
        events.append({
            "id": str(r.id), "agent": r.agent.value, "label": meta["label"], "icon": meta["icon"],
            "channel": c.telegram_username if c else None,
            "channel_id": str(r.channel_id) if r.channel_id else None,
            "action": _ACTION_VERB.get(r.status, r.status.value),
            "result": _compact_summary(r.output_summary),
            "status": _STATUS_MAP.get(r.status, r.status.value),
            "ts": r.started_at.isoformat() if r.started_at else None,
            "reason": (r.error or "")[:160] if r.status == RunStatus.failed else None,
        })
    return events


async def admin_system_health(session: AsyncSession) -> dict:
    chans = {c.id: c for c in (await session.execute(select(Channel))).scalars().all()}
    channel_health = []
    for cid_, c in chans.items():
        runs = (await session.execute(
            select(AgentRun).where(AgentRun.channel_id == cid_).order_by(AgentRun.started_at.desc()).limit(15)
        )).scalars().all()
        latest: dict[str, AgentRun] = {}
        for r in runs:
            latest.setdefault(r.agent.value, r)
        latest_failed = any(r.status == RunStatus.failed for r in latest.values())
        any_failed = any(r.status == RunStatus.failed for r in runs)
        health = "red" if latest_failed else ("yellow" if any_failed else "green")
        channel_health.append({"channel": c.telegram_username, "channel_id": str(cid_),
                               "health": health, "runs": len(runs)})
    fails = (await session.execute(
        select(AgentRun).where(AgentRun.status == RunStatus.failed).order_by(AgentRun.started_at.desc()).limit(15)
    )).scalars().all()
    recent_failures = [{
        "agent": f.agent.value,
        "channel": chans[f.channel_id].telegram_username if f.channel_id in chans else None,
        "error": (f.error or "")[:200],
        "ts": f.started_at.isoformat() if f.started_at else None,
    } for f in fails]
    return {"channel_health": channel_health, "recent_failures": recent_failures}


# ── Manual agent runner ──────────────────────────────────────────────────────
KNOWN_AGENTS = {"onboard", "dna", "competitor", "analytics", "strategy", "content"}


async def run_agent(channel_id: str, username: str | None, agent: str, snapshot_type: str = "daily",
                    task_id: str | None = None, with_telegram: bool = True) -> dict:
    """Run an agent on demand. Telegram-dependent agents open a Telethon session.

    Takes plain ids/strings (not an ORM object) so it can run in a background
    task after the request's DB session has closed.
    """
    from agents.analytics import AnalyticsAgent
    from agents.channel_dna import ChannelDNAAgent
    from agents.competitor_intelligence import CompetitorIntelligenceAgent
    from agents.content_intelligence import ContentIntelligenceAgent
    from agents.strategy import StrategyAgent
    from tools.telegram_client import telethon_session

    cid = str(channel_id)
    uname = username

    if agent == "onboard":  # tier-aware full initial pipeline
        from scheduler.jobs import onboard_channel_pipeline
        return await onboard_channel_pipeline(cid)

    if agent == "strategy":  # no telegram needed
        return await StrategyAgent(snapshot_type, trigger="manual").run(cid)

    if agent == "content":
        if not task_id:
            raise ValueError("content agent requires task_id")
        if with_telegram:
            async with telethon_session() as c:
                return await ContentIntelligenceAgent(trigger="manual").run(cid, task_id=task_id, client=c)
        return await ContentIntelligenceAgent(trigger="manual").run(cid, task_id=task_id)

    # dna / competitor / analytics need telegram
    async with telethon_session() as c:
        if agent == "dna":
            return await ChannelDNAAgent(trigger="manual").run(cid, username=uname, client=c)
        if agent == "competitor":
            return await CompetitorIntelligenceAgent(trigger="manual").run(cid, client=c)
        if agent == "analytics":
            return await AnalyticsAgent(snapshot_type, trigger="manual").run(cid, username=uname, client=c)
    raise ValueError(f"unknown agent {agent!r}")
