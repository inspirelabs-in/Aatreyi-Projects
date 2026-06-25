"""Analytics tools (Phase 4).

Rule-based daily/weekly snapshots per formulae.md §3: subscriber delta, avg
views/ER, reach estimate, churn signal, and the 6 insight rules.
compute_analytics_snapshot does no I/O and is fully unit-testable.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, time as _time, timezone
from typing import Any

from sqlalchemy import delete, select

from db.base import AsyncSessionLocal
from db.models import AnalyticsSnapshot, Channel, ChannelDNA, SnapshotType
from tools.channel_dna import _er_post

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAYS_BY_TYPE = {"daily": 1, "weekly": 7, "monthly": 30}


# ── ER by format / best slots (pure) ─────────────────────────────────────────
def compute_er_by_format(posts: list[dict], subscriber_count: int | None = None) -> dict[str, float]:
    by_fmt: dict[str, list[float]] = defaultdict(list)
    for p in posts:
        er = _er_post(p, subscriber_count)
        if er is not None:
            by_fmt[p.get("format") or "text"].append(er)
    return {f: round(sum(v) / len(v), 3) for f, v in by_fmt.items() if v}


def compute_best_slots(posts: list[dict], subscriber_count: int | None = None) -> dict[str, Any]:
    """argmax ER over hour and weekday buckets."""
    by_hour: dict[int, list[float]] = defaultdict(list)
    by_day: dict[str, list[float]] = defaultdict(list)
    for p in posts:
        er = _er_post(p, subscriber_count)
        dt = p.get("posted_at")
        if er is None or dt is None:
            continue
        by_hour[dt.hour].append(er)
        by_day[WEEKDAYS[dt.weekday()]].append(er)
    best_hour = max(by_hour, key=lambda h: sum(by_hour[h]) / len(by_hour[h])) if by_hour else None
    best_day = max(by_day, key=lambda d: sum(by_day[d]) / len(by_day[d])) if by_day else None
    return {"best_hour": best_hour, "best_day": best_day}


def _reach_estimate(posts: list[dict], subscriber_count: int | None) -> int | None:
    """formulae.md §3.3: max over posts of views*(1 + forwards/subs*5)."""
    subs = subscriber_count or 0
    best = 0.0
    seen = False
    for p in posts:
        views = p.get("views") or 0
        if views <= 0:
            continue
        seen = True
        fwd = p.get("forwards") or 0
        mult = 1.0 if fwd == 0 or subs <= 0 else 1.0 + (fwd / subs) * 5.0
        best = max(best, views * mult)
    return int(round(best)) if seen else None


SUSTAINED_DECLINE_PERIODS = 3  # consecutive shrinking periods => slow-bleed churn


def detect_sustained_decline(current_delta_pct: float | None, prior_pcts: list[float],
                             min_periods: int = SUSTAINED_DECLINE_PERIODS) -> bool:
    """Slow-bleed churn: subscribers shrink for `min_periods` consecutive periods.

    Complements the spike detector — catches a steady decline (e.g. -0.3%/day for
    several days) that never spikes but is genuine churn. Applies to every channel.
    """
    if current_delta_pct is None or current_delta_pct >= 0:
        return False
    recent = [current_delta_pct] + list(prior_pcts[:min_periods - 1])
    return len(recent) >= min_periods and all(p is not None and p < 0 for p in recent)


def classify_churn_risk(delta_pct: float | None, churn_signal: bool) -> str:
    """Grade churn risk from the period's subscriber change + the spike signal.

    high   : a churn spike (unsubscribes > 2x rolling avg) OR a sharp drop (<= -2%)
    medium : a clear decline (<= -0.5%)
    low    : a mild dip (< 0%)
    none   : flat or growing
    """
    if delta_pct is None:
        return "unknown"
    if churn_signal or delta_pct <= -2.0:
        return "high"
    if delta_pct <= -0.5:
        return "medium"
    if delta_pct < 0:
        return "low"
    return "none"


def build_daily_history_from_posts(posts: list[dict], member_count: int | None) -> list[dict]:
    """Derive a REAL per-day analytics history from the channel's actual posts.

    Telegram exposes real post metrics (views/forwards/reactions, dated) but not
    historical subscriber counts — so each day's snapshot carries real ER / views
    / volume / post-intelligence, with subscriber_count = current (no fabricated
    growth; subscriber_delta is left null). Returns snapshot dicts (oldest first).
    """
    from collections import defaultdict
    from datetime import date as _date
    from tools.intelligence import compute_post_intelligence, post_er
    from tools.retention import recycle_candidates

    by_day: dict = defaultdict(list)
    for p in posts:
        pa = p.get("posted_at")
        if not pa:
            continue
        d = pa.date() if hasattr(pa, "date") else _date.fromisoformat(str(pa)[:10])
        by_day[d].append(p)

    snaps = []
    for d in sorted(by_day):
        dp = by_day[d]
        views = [p.get("views") or 0 for p in dp]
        ers = [post_er(p) for p in dp]
        intel = compute_post_intelligence(dp, member_count)
        intel["recycle_candidates"] = recycle_candidates(dp)
        # real insights derived from the day's actual posts
        insights = []
        if intel["spikes"]:
            insights.append({"type": "growth", "note": f"{intel['spikes']} break-out post(s) this day"})
        fe = intel["format_engagement"]
        if len(fe) >= 2 and fe[0]["avg_er"] > 0:
            insights.append({"type": "format", "note": f"{fe[0]['label']} engaged best ({fe[0]['avg_er']}% ER)"})
        snaps.append({
            "snapshot_type": "daily",
            "period_start": d.isoformat(), "period_end": d.isoformat(),
            # historical subscriber counts aren't available from Telegram — leave
            # null (not a fake-flat current value). The live count/growth come from
            # the high-frequency subscriber_readings instead.
            "subscriber_count": None, "subscriber_delta": None, "subscriber_delta_pct": None,
            "avg_views": round(sum(views) / len(views), 2) if views else None,
            "avg_er": round(sum(ers) / len(ers), 3) if ers else None,
            "total_posts": len(dp), "churn_signal": False, "churn_type": None,
            "insights": insights, "intelligence": intel,
            "_day": d,
        })
    return snaps


async def save_real_daily_history(channel_id: str | uuid.UUID, posts: list[dict],
                                  member_count: int | None) -> int:
    """Persist a REAL daily analytics history from actual posts (clears prior
    daily snapshots first so the timeline is consistent). Called on onboarding so
    a channel isn't an empty chart on day 1. Returns the number of days saved."""
    snaps = build_daily_history_from_posts(posts, member_count)
    if not snaps:
        return 0
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AnalyticsSnapshot).where(
            AnalyticsSnapshot.channel_id == cid, AnalyticsSnapshot.snapshot_type == SnapshotType.daily))
        for snap in snaps:
            d = snap["_day"]
            session.add(AnalyticsSnapshot(
                channel_id=cid, snapshot_type=SnapshotType.daily,
                period_start=d, period_end=d, subscriber_count=snap["subscriber_count"],
                avg_views=snap["avg_views"], avg_er=snap["avg_er"], total_posts=snap["total_posts"],
                churn_signal=False, insights=snap["insights"], intelligence=snap["intelligence"],
                created_at=datetime.combine(d, _time(12, 0), tzinfo=timezone.utc),
            ))
        await session.commit()
    return len(snaps)


# ── Core snapshot computation (pure) ─────────────────────────────────────────
def compute_analytics_snapshot(
    *,
    channel_id: str,
    current_member_count: int,
    posts: list[dict],
    previous_snapshot: dict | None = None,
    snapshot_type: str = "daily",
    period_start: str | None = None,
    period_end: str | None = None,
    history: list[dict] | None = None,
    target_post_frequency: float | None = None,
) -> dict[str, Any]:
    """Return a snapshot payload matching analytics_snapshots schema.

    `history` = prior snapshots of the same type (dicts with subscriber_delta_pct,
    avg_er); used for churn rolling-average and the best_growth_day rule.
    """
    history = history or []
    prev = previous_snapshot or {}
    days_in_period = _DAYS_BY_TYPE.get(snapshot_type, 1)

    payload: dict[str, Any] = {
        "snapshot_type": snapshot_type,
        "period_start": period_start,
        "period_end": period_end,
        "subscriber_count": current_member_count,
        "subscriber_delta": None,
        "subscriber_delta_pct": None,
        "avg_views": None,
        "avg_er": None,
        "total_posts": len(posts),
        "reach": None,
        "churn_signal": False,
        "churn_rate": None,
        "churn_type": None,
        "insights": [],
    }

    # subscriber delta (§3.1)
    prev_count = prev.get("subscriber_count")
    if prev_count:
        delta = current_member_count - prev_count
        payload["subscriber_delta"] = delta
        payload["subscriber_delta_pct"] = round(delta / prev_count * 100, 3)

    # views / ER (None when no posts, per agent rules)
    if posts:
        views_vals = [p.get("views") or 0 for p in posts]
        payload["avg_views"] = round(sum(views_vals) / len(views_vals), 2)
        er_vals = [er for p in posts if (er := _er_post(p, current_member_count)) is not None]
        payload["avg_er"] = round(sum(er_vals) / len(er_vals), 3) if er_vals else None
        payload["reach"] = _reach_estimate(posts, current_member_count)

    # churn (§3.4)
    cur_pct = payload["subscriber_delta_pct"]
    if cur_pct is not None:
        payload["churn_rate"] = round(abs(min(cur_pct, 0.0)), 3)
        prior_pcts = [
            h["subscriber_delta_pct"] for h in history[:4]
            if h.get("subscriber_delta_pct") is not None
        ]
        if prior_pcts and payload["subscriber_delta"] is not None and payload["subscriber_delta"] < 0:
            rolling = sum(prior_pcts) / len(prior_pcts)
            if payload["churn_rate"] > 2 * abs(rolling):
                payload["churn_signal"] = True          # sudden spike
        # slow steady bleed: shrinking N periods in a row (no spike needed)
        if detect_sustained_decline(cur_pct, prior_pcts):
            payload["churn_signal"] = True
            payload["churn_type"] = "sustained"
        elif payload["churn_signal"]:
            payload["churn_type"] = "spike"
    payload["churn_risk"] = classify_churn_risk(cur_pct, payload["churn_signal"])

    payload["insights"] = _build_insights(
        payload, prev, history, posts, snapshot_type, days_in_period, target_post_frequency
    )
    return payload


def _build_insights(payload, prev, history, posts, snapshot_type, days_in_period, target_freq) -> list[dict]:
    insights: list[dict] = []
    cur_pct = payload["subscriber_delta_pct"]
    cur_er = payload["avg_er"]
    prev_er = prev.get("avg_er")

    # RULE 1 — best_growth_day (daily only)
    if snapshot_type == "daily" and cur_pct is not None and cur_pct > 0:
        prior_pcts = [h["subscriber_delta_pct"] for h in history if h.get("subscriber_delta_pct") is not None]
        if not prior_pcts or cur_pct >= max(prior_pcts):
            insights.append({"type": "growth", "note": "Best single-day gain this month"})

    # RULE 2 / 3 — ER drop / spike
    if cur_er is not None and prev_er:
        if cur_er < prev_er * 0.70:
            insights.append({"type": "er_drop", "note": "ER fell >30% vs last period"})
        elif cur_er > prev_er * 1.30:
            insights.append({"type": "er_spike", "note": "ER up >30% vs last period"})

    # RULE 4 — format_winner
    er_by_fmt = compute_er_by_format(posts, payload["subscriber_count"])
    if len(er_by_fmt) >= 2:
        best_fmt = max(er_by_fmt, key=er_by_fmt.get)
        worst_fmt = min(er_by_fmt, key=er_by_fmt.get)
        if er_by_fmt[worst_fmt] > 0 and er_by_fmt[best_fmt] > er_by_fmt[worst_fmt] * 2.0:
            insights.append({"type": "format", "note": f"{best_fmt} outperforming {worst_fmt} 2×"})

    # RULE 5 — low_post_volume
    if target_freq:
        target_total = round(target_freq * days_in_period * 0.6)
        if payload["total_posts"] < target_total:
            insights.append({"type": "volume", "note": "Post volume 40% below target cadence"})

    # RULE 6 — churn_alert (spike or slow sustained bleed)
    if payload["churn_signal"]:
        note = ("Sustained decline — subscribers shrinking several periods in a row"
                if payload.get("churn_type") == "sustained"
                else "Churn spike detected — unsubscribes 2× rolling average")
        insights.append({"type": "churn", "note": note})

    return insights


def generate_analytics_digest(snapshot: dict) -> str:
    """Template-based text summary (no LLM)."""
    lines = [
        f"📊 {snapshot.get('snapshot_type', 'daily').title()} report",
        f"Subscribers: {snapshot.get('subscriber_count')} "
        f"({_signed(snapshot.get('subscriber_delta'))}, {_signed(snapshot.get('subscriber_delta_pct'))}%)",
        f"Avg views: {snapshot.get('avg_views')} | Avg ER: {snapshot.get('avg_er')}% | Posts: {snapshot.get('total_posts')}",
    ]
    for ins in snapshot.get("insights", []) or []:
        lines.append(f"• {ins.get('note')}")
    return "\n".join(lines)


def _signed(v) -> str:
    if v is None:
        return "n/a"
    return f"+{v}" if v >= 0 else str(v)


# ── Persistence / loaders ────────────────────────────────────────────────────
_SNAPSHOT_COLUMNS = {
    "snapshot_type", "period_start", "period_end", "subscriber_count",
    "subscriber_delta", "subscriber_delta_pct", "avg_views", "avg_er",
    "total_posts", "reach", "churn_signal", "churn_rate", "insights",
    "intelligence",
}


def _to_date(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v).date()
    return v


async def save_analytics_snapshot(channel_id: str | uuid.UUID, snapshot: dict) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    fields = {k: v for k, v in snapshot.items() if k in _SNAPSHOT_COLUMNS}
    fields["period_start"] = _to_date(fields.get("period_start"))
    fields["period_end"] = _to_date(fields.get("period_end"))
    async with AsyncSessionLocal() as session:
        row = AnalyticsSnapshot(channel_id=cid, **fields)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return {"success": True, "record_id": str(row.id)}


def _snapshot_to_dict(row: AnalyticsSnapshot) -> dict[str, Any]:
    return {
        "subscriber_count": row.subscriber_count,
        "subscriber_delta": row.subscriber_delta,
        "subscriber_delta_pct": row.subscriber_delta_pct,
        "avg_views": row.avg_views,
        "avg_er": row.avg_er,
        "total_posts": row.total_posts,
        "churn_signal": row.churn_signal,
        "snapshot_type": row.snapshot_type.value if row.snapshot_type else None,
    }


async def get_previous_snapshot(channel_id: str | uuid.UUID, snapshot_type: str) -> dict | None:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(AnalyticsSnapshot)
                .where(
                    AnalyticsSnapshot.channel_id == cid,
                    AnalyticsSnapshot.snapshot_type == SnapshotType(snapshot_type),
                )
                .order_by(AnalyticsSnapshot.created_at.desc())
            )
        ).scalars().first()
        return _snapshot_to_dict(row) if row else None


async def get_analytics_history(channel_id: str | uuid.UUID, snapshot_type: str, n: int = 30) -> list[dict]:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(AnalyticsSnapshot)
                .where(
                    AnalyticsSnapshot.channel_id == cid,
                    AnalyticsSnapshot.snapshot_type == SnapshotType(snapshot_type),
                )
                .order_by(AnalyticsSnapshot.created_at.desc())
                .limit(n)
            )
        ).scalars().all()
        return [_snapshot_to_dict(r) for r in rows]


async def flag_strategy_review(channel_id: str | uuid.UUID, reason: str) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(Channel).where(Channel.id == cid))
        ).scalar_one_or_none()
        if row is None:
            return {"flagged": False}
        row.needs_strategy_review = True
        row.strategy_review_reason = reason
        await session.commit()
    return {"flagged": True}


async def get_target_post_frequency(channel_id: str | uuid.UUID) -> float | None:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        dna = (
            await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))
        ).scalar_one_or_none()
        return dna.post_frequency_per_day if dna else None
