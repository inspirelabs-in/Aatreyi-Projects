"""Strategy tools (Phase 5).

Rule-based weekly/daily plan per formulae.md §4 + the roadmap growth-tactics
table: recommended cadence, content mix, min-gap slot times, competitor-gap
topics, and per-slot tasks. compute_strategy is pure / unit-testable.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select

from config import settings
from db.base import AsyncSessionLocal
from tools.analytics import classify_churn_risk
from tools.retention import build_retention_triggers, fatigue_score
from db.models import (
    AnalyticsSnapshot,
    CadenceLabel,
    Channel,
    ChannelDNA,
    Competitor,
    CronJob,
    SnapshotType,
    Strategy,
    StrategyStatus,
    StrategyTask,
    StrategyType,
    TaskStatus,
)

FREQ_MIN, FREQ_MAX = 1.0, 5.0
SLOT_MIN_GAP = 3  # hours between slots (formulae.md §4.3)
ALL_FORMATS = ["article", "poll", "meme", "video", "link"]
_DAYS_BY_TYPE = {"daily": 1, "weekly": 7, "monthly": 30}

# Post slots are planned, stored and fired in this timezone (default IST) so the
# recommended times match the channel's real-world audience clock.
LOCAL_TZ = ZoneInfo(settings.SCHEDULER_TIMEZONE)


def utc_hour_to_local(h: int) -> int:
    """Map an integer UTC hour-of-day to the nearest local hour (rounds :30)."""
    base = datetime(2025, 1, 1, h % 24, tzinfo=timezone.utc).astimezone(LOCAL_TZ)
    return (base.hour + (1 if base.minute >= 30 else 0)) % 24


# ── Recommended frequency (§4.1) ─────────────────────────────────────────────
def recommended_frequency(base_freq: float | None, subscriber_delta_pct: float | None,
                          avg_er: float | None, declining: bool = False) -> float:
    base = base_freq or 1.0
    boost = 0.0
    if subscriber_delta_pct is not None:
        if subscriber_delta_pct > 10:
            boost = 1.0
        elif subscriber_delta_pct > 5:
            boost = 0.5
    penalty = 0.5 if (avg_er is not None and avg_er < 1.5) else 0.0
    # `declining` executes the reduce_frequency tactic: over-posting to a shrinking
    # audience accelerates churn, so cut a full post/day.
    decline_cut = 1.0 if declining else 0.0
    return max(FREQ_MIN, min(base + boost - penalty - decline_cut, FREQ_MAX))


# ── Content mix (§4.2) ───────────────────────────────────────────────────────
def _normalise_to_pct(weights: dict[str, float]) -> list[dict]:
    total = sum(weights.values())
    if total <= 0:
        return []
    pcts = {f: round(w / total * 100) for f, w in weights.items() if w > 0}
    # fix rounding drift so the mix sums to exactly 100
    drift = 100 - sum(pcts.values())
    if pcts and drift:
        top = max(pcts, key=pcts.get)
        pcts[top] += drift
    return [{"format": f, "pct": p} for f, p in sorted(pcts.items(), key=lambda kv: kv[1], reverse=True)]


def compute_content_mix(
    top_content_formats: list[dict] | None,
    er_by_format: dict[str, float] | None,
    channel_avg_er: float | None,
    avg_er: float | None,
) -> list[dict]:
    base: dict[str, float] = {}
    for entry in top_content_formats or []:
        base[entry.get("format", "article")] = float(entry.get("share") or 0)
    if not base:
        base = {"article": 0.5, "poll": 0.3, "meme": 0.2}

    # ER boost per format (§4.2) when available
    if er_by_format and channel_avg_er:
        adjusted = {
            f: w * (1 + (er_by_format.get(f, channel_avg_er) - channel_avg_er) / channel_avg_er)
            for f, w in base.items()
        }
        adjusted = {f: max(w, 0.0) for f, w in adjusted.items()}
    else:
        adjusted = dict(base)

    # Rule: ER < 3% -> raise poll share to 40% of the mix
    if avg_er is not None and avg_er < 3:
        others_total = sum(w for f, w in adjusted.items() if f != "poll") or 1.0
        scaled = {f: (w / others_total) * 0.6 for f, w in adjusted.items() if f != "poll"}
        scaled["poll"] = 0.4
        adjusted = scaled
    # Rule: ER > 8% -> hold mix (no change)

    return _normalise_to_pct(adjusted)


# ── Slot assignment (§4.3) ───────────────────────────────────────────────────
def _hour_scores(best_post_hour: int | None, avg_er_by_hour: dict[int, float] | None) -> dict[int, float]:
    if avg_er_by_hour:
        return {int(h): float(v) for h, v in avg_er_by_hour.items()}
    peak = best_post_hour if best_post_hour is not None else 18
    scores: dict[int, float] = {}
    for h in range(24):
        dist = min(abs(h - peak), 24 - abs(h - peak))  # circular distance
        scores[h] = max(0.0, 1.0 - dist / 12.0)
    return scores


def greedy_select_slots(scores: dict[int, float], n: int, min_gap: int = SLOT_MIN_GAP) -> list[int]:
    """Pick n highest-scoring hours that are >= min_gap hours apart."""
    selected: list[int] = []
    for h in sorted(scores, key=lambda x: (-scores[x], x)):
        if len(selected) >= n:
            break
        if all(abs(h - s) >= min_gap for s in selected):
            selected.append(h)
    return sorted(selected)


# ── Competitor gap topics (§ Jaccard complement) ─────────────────────────────
def get_competitor_gap_topics(my_topics: set[str], competitors: list[dict]) -> list[str]:
    """Themes competitors cover that we don't — used to widen content topics.

    Bare category labels ("tech", "crypto", "news"…) are dropped: they are coarse
    classifications, not content topics, and when a channel's competitor set is
    off-niche they would otherwise pollute an unrelated channel's plan (e.g. an
    entertainment channel getting "business/crypto" slots). Only specific themes
    survive as gaps; the channel's own DNA topics remain the primary source.
    """
    from tools.channel_dna import CATEGORY_KEYWORDS

    category_labels = set(CATEGORY_KEYWORDS.keys())
    competitor_themes: set[str] = set()
    for c in competitors or []:
        for t in (c.get("top_themes") or c.get("top_content_themes") or []):
            competitor_themes.add(str(t).lower())
    gaps = competitor_themes - {t.lower() for t in my_topics} - category_labels
    return sorted(gaps)


# ── Growth tactics (roadmap rules table) ─────────────────────────────────────
def competitor_avg_er(competitors) -> float | None:
    ers = [c.get("avg_er") for c in (competitors or []) if c.get("avg_er") is not None]
    return round(sum(ers) / len(ers), 3) if ers else None


def _has_valid_competitor_data(competitors: list) -> bool:
    """True only when at least one competitor has real ER data.

    Competitors are often discovered by name but their Telegram handles can't be
    resolved via free search (no member_count, no avg_er). A non-empty competitors
    list therefore doesn't mean the data is usable for benchmarking.
    """
    return any(c.get("avg_er") is not None for c in (competitors or []))


def _tactic(name, severity, why, action) -> dict:
    # `detail` kept for back-compat; `why` (root cause) + `action` (what + why it works)
    # give the deeper reasoning the UI surfaces.
    return {"tactic": name, "severity": severity, "why": why, "action": action, "detail": action}


def build_growth_tactics(avg_er, churn_signal, subscriber_delta, competitors, my_avg_er,
                         er_by_format: dict | None = None) -> list[dict]:
    """Diagnose WHY the channel is where it is, then prescribe an action that
    follows from the cause — not just a label. Each tactic carries `why`
    (root-cause) + `action` (what to do and why it works)."""
    tactics: list[dict] = []
    bench = competitor_avg_er(competitors)

    if avg_er is not None and avg_er < 3:
        gap = f"{round(3 / avg_er, 1)}x under" if avg_er else "far under"
        tactics.append(_tactic(
            "increase_polls", "high" if avg_er < 1 else "medium",
            why=(f"Engagement is {avg_er}% — {gap} the ~3% healthy floor. Followers see posts but "
                 "rarely react, which means the content is passive (nothing asks them to act) and "
                 "Telegram's reach favours high-interaction channels, so low ER quietly suppresses "
                 "future reach too — a downward spiral."),
            action=("Raise poll share to ~40% of the mix. A poll needs one tap, so it converts silent "
                    "viewers into measurable engagement immediately, and the result itself sparks more "
                    "reaction — the fastest lever to break the spiral."),
        ))
    if avg_er is not None and avg_er > 8:
        tactics.append(_tactic(
            "hold_mix", "low",
            why=f"ER is {avg_er}% — already strong, so the current format mix is resonating.",
            action="Hold the format mix; change one variable at a time so you don't break what works.",
        ))
    if subscriber_delta is not None and subscriber_delta < 0:
        tactics.append(_tactic(
            "reduce_frequency", "high",
            why=(f"You lost {abs(subscriber_delta)} subscribers this period. When engagement is low, "
                 "posting more often backfires: each weak, low-value post is another notification that "
                 "gives a member a reason to mute or leave."),
            action=("Applied: this plan cuts posting by 1/day and raises the bar per post (stronger hook, "
                    "clearer payoff) until ER recovers — fewer, better posts reduce the unsubscribe trigger."),
        ))
    # ── retention ──
    if churn_signal:
        tactics.append(_tactic(
            "strategy_reset", "high",
            why=("A churn spike means the audience is actively leaving — that's a value mismatch, not a "
                 "tuning problem. Incremental tweaks won't fix content the audience no longer wants."),
            action=("Re-profile the audience and rebuild the topic/format plan from the formats that win "
                    "for top competitors, rather than iterating on the losing plan."),
        ))
        tactics.append(_tactic(
            "re_engage", "medium",
            why=("Churning members were once interested, so winning them back is far cheaper than "
                 "acquiring new ones — and re-engagement lifts the ER that drives reach."),
            action="Applied: a re-engagement poll has been scheduled as the first slot of this plan to pull lapsed members back.",
        ))
    # ── benchmark vs competitors ──
    if bench is not None and my_avg_er is not None and my_avg_er < bench:
        mult = f"{round(bench / my_avg_er, 1)}x" if my_avg_er else "many times"
        tactics.append(_tactic(
            "close_er_gap", "high",
            why=(f"Competitors average {bench}% ER versus your {my_avg_er}% — a {mult} gap. With a similar "
                 "audience, far less reaction points to weaker hooks, CTAs, or a format mismatch for what "
                 "this niche actually rewards."),
            action=(f"Reverse-engineer the top competitor's highest-ER posts (hook, length, media, CTA), "
                    f"copy the pattern, and target ER {bench}%."),
        ))
    top = max(competitors or [], key=lambda c: c.get("avg_er") or 0, default=None)
    if top and (top.get("avg_er") or 0) > (my_avg_er or 0):
        tactics.append(_tactic(
            "mirror_format", "medium",
            why=(f"@{top.get('username')} leads the set at {top.get('avg_er')}% ER — in this niche their "
                 "dominant format is what the audience rewards most."),
            action="Replicate their top-performing format for 2 weeks and measure the ER lift before scaling it.",
        ))

    # ── self-benchmark fallback ───────────────────────────────────────────────
    # When no competitor has usable ER data (names found but handles unresolved,
    # or competitor agent hasn't run yet), fall back to the channel's own format
    # performance — the highest-ER format from DNA is the best signal available.
    if not _has_valid_competitor_data(competitors) and er_by_format and my_avg_er is not None:
        top_fmt = max(er_by_format, key=er_by_format.get)
        top_fmt_er = round(er_by_format[top_fmt], 2)
        if top_fmt_er > my_avg_er:
            mult = round(top_fmt_er / my_avg_er, 1) if my_avg_er else "—"
            tactics.append(_tactic(
                "self_benchmark_boost", "medium",
                why=(f"No competitor ER data is available yet (competitors discovered but handles "
                     f"unresolved). Self-benchmarking instead: '{top_fmt}' posts average "
                     f"{top_fmt_er}% ER on this channel — {mult}x above the channel average "
                     f"({my_avg_er}%). That's the strongest signal available."),
                action=(f"Applied: boosted '{top_fmt}' share in the content mix to lean into your "
                        f"own best-performing format. Run competitor agent again once channels are "
                        f"resolved to get external benchmarks."),
            ))

    return tactics


def build_diagnosis(avg_er, subscriber_delta, churn_signal, bench, tactics) -> str:
    """One-paragraph root-cause summary tying the signals together."""
    parts = []
    if avg_er is not None:
        if bench is not None and avg_er < bench:
            mult = f"{round(bench / avg_er, 1)}x " if avg_er else ""
            parts.append(f"Engagement ({avg_er}%) is {mult}below the competitor average ({bench}%)")
        else:
            parts.append(f"Engagement is {avg_er}%")
    if churn_signal:
        parts.append("the audience is actively churning")
    elif subscriber_delta is not None:
        parts.append(f"net subscribers moved {'+' if subscriber_delta >= 0 else ''}{subscriber_delta}")
    lead = tactics[0] if tactics else None
    tail = f" Primary lever: {lead['tactic'].replace('_', ' ')}." if lead else ""
    return ("; ".join(parts) + "." + tail) if parts else "Insufficient data for a full diagnosis yet."


# ── Core (pure) ──────────────────────────────────────────────────────────────
def compute_strategy(
    inputs: dict,
    strategy_type: str = "weekly",
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict[str, Any]:
    """Build a strategy_payload (goal, cadence, mix, topics, tactics, tasks)."""
    dna = inputs.get("dna") or {}
    analytics = inputs.get("analytics_daily") or inputs.get("analytics_weekly") or {}
    competitors = inputs.get("competitors") or []
    er_by_format = inputs.get("er_by_format")

    community_state = inputs.get("community_state")
    recycle_candidates = inputs.get("recycle_candidates") or []

    avg_er = dna.get("avg_er")
    delta_pct = analytics.get("subscriber_delta_pct")
    churn = analytics.get("churn_signal")
    sub_delta = analytics.get("subscriber_delta")

    declining = bool(churn) or (sub_delta is not None and sub_delta < 0)
    freq = recommended_frequency(dna.get("post_frequency_per_day"), delta_pct, avg_er, declining=declining)
    slots_per_day = max(1, round(freq))

    content_mix = compute_content_mix(
        dna.get("top_content_formats"), er_by_format, avg_er, avg_er
    )

    # specific DNA-mined topics first, then category fallback, then competitor gaps
    cat_topics = {t for t in (dna.get("category"), dna.get("sub_category")) if t}
    specific = list(dna.get("top_topics") or [])
    base_topics = specific or [t for t in cat_topics]
    gaps = get_competitor_gap_topics(cat_topics | set(base_topics), competitors)
    primary_topics = list(dict.fromkeys([t for t in (base_topics + gaps) if t]))[:6] or ["general"]

    tactics = build_growth_tactics(avg_er, churn, sub_delta, competitors, avg_er,
                                   er_by_format=er_by_format)
    bench_er = competitor_avg_er(competitors)
    valid_competitor_data = _has_valid_competitor_data(competitors)
    target_er = bench_er if (bench_er is not None and (avg_er is None or bench_er > avg_er)) else avg_er

    # Execute close_er_gap / mirror_format: when behind competitors, lean the mix
    # into the channel's highest-ER format (measured by the Analytics agent).
    # Fallback: when no competitor ER data exists at all, self-benchmark using the
    # channel's own best-performing format — the mix is always data-driven.
    top_er_format = max(er_by_format, key=er_by_format.get) if er_by_format else None
    behind = bench_er is not None and avg_er is not None and bench_er > avg_er
    if behind and top_er_format:
        content_mix = boost_format(content_mix, top_er_format)
        for t in tactics:
            if t["tactic"] in ("close_er_gap", "mirror_format"):
                t["action"] += f" Applied: boosted '{top_er_format}' (your highest-ER format) in the mix."
    elif not valid_competitor_data and top_er_format and er_by_format:
        self_top_er = er_by_format[top_er_format]
        if self_top_er > (avg_er or 0):
            content_mix = boost_format(content_mix, top_er_format)

    # slot hours — engagement data is UTC-keyed; convert to the local clock so
    # selected slots (and the no-data default of ~6 PM) land in audience time.
    best_hour = dna.get("best_post_hour")
    best_local = utc_hour_to_local(best_hour) if best_hour is not None else None
    raw_by_hour = inputs.get("avg_er_by_hour") or {}
    local_by_hour = {utc_hour_to_local(int(h)): float(v) for h, v in raw_by_hour.items()} or None
    scores = _hour_scores(best_local, local_by_hour)
    slot_hours = greedy_select_slots(scores, slots_per_day)  # local hours

    # dates
    ps = date.fromisoformat(period_start) if period_start else date.today() + timedelta(days=1)
    days = _DAYS_BY_TYPE.get(strategy_type, 7)
    pe = date.fromisoformat(period_end) if period_end else ps + timedelta(days=days - 1)

    # build tasks: weighted formats round-robin, topics round-robin
    format_cycle = _weighted_format_cycle(content_mix)
    tasks: list[dict] = []
    fi = ti = 0
    cur = ps
    while cur <= pe:
        for h in slot_hours:
            tasks.append({
                "scheduled_date": cur.isoformat(),
                "scheduled_time": f"{h:02d}:00",
                "format": format_cycle[fi % len(format_cycle)] if format_cycle else "article",
                "topic": primary_topics[ti % len(primary_topics)],
                "kind": None,
            })
            fi += 1
            ti += 1
        cur += timedelta(days=1)

    # Phase 2: execute retention. When there's a retention concern (churn, weak
    # engagement, or a silent community), schedule habit-loop triggers as the
    # first slots — gated so healthy active channels keep their plain plan.
    retention_concern = (
        bool(churn)
        or (avg_er is not None and avg_er < 2.0)
        or community_state == "silent"
    )
    retention_triggers = []
    if retention_concern and tasks:
        risk = classify_churn_risk(delta_pct, bool(churn))
        retention_triggers = build_retention_triggers(
            risk, community_state, primary_topics[0] if primary_topics else None,
            series_day=inputs.get("series_day", 1),
        )
        # Place one trigger per day on that day's first slot — REPLACING regular
        # content, not adding to it — so retention posts are spread across days
        # (distinct times) and don't inflate the cadence (respects reduce_frequency).
        for i, trig in enumerate(retention_triggers):
            idx = i * slots_per_day
            if idx >= len(tasks):
                break
            tasks[idx] = {
                "scheduled_date": tasks[idx]["scheduled_date"],
                "scheduled_time": tasks[idx]["scheduled_time"],
                "format": trig["format"],
                "topic": trig["topic"],
                "kind": trig["kind"],
            }
    if recycle_candidates:
        _inject_recycle_slots(tasks, recycle_candidates, slots_per_day)
    fatigue = fatigue_score(tasks)

    goal = (
        f"Grow {dna.get('category') or 'channel'}: {slots_per_day} post(s)/day, "
        f"focus {', '.join(primary_topics[:3])}"
    )
    if bench_er is not None and avg_er is not None and bench_er > avg_er:
        goal += f". Close ER gap to competitor avg {bench_er}% (current {avg_er}%)"
    diagnosis = build_diagnosis(avg_er, sub_delta, churn, bench_er, tactics)
    return {
        "goal": goal,
        "diagnosis": diagnosis,
        "post_frequency_per_day": freq,
        "content_mix": content_mix,
        "primary_topics": primary_topics,
        "growth_tactics": tactics,
        "benchmark": {
            "competitor_avg_er": bench_er,
            "my_avg_er": avg_er,
            "target_er": target_er,
        },
        "retention_plan": retention_triggers,
        "fatigue": fatigue,
        "period_start": ps.isoformat(),
        "period_end": pe.isoformat(),
        "tasks": tasks,
    }


def _inject_recycle_slots(
    tasks: list[dict], recycle_candidates: list[dict], slots_per_day: int
) -> None:
    """Replace one slot per day (from day 2 onward) with a recycle task in a fresh format."""
    if not recycle_candidates or not tasks or slots_per_day < 1:
        return
    alt = {"text": "poll", "poll": "photo", "photo": "text", "video": "text", "link": "text",
           "article": "poll", "meme": "text"}
    for i, cand in enumerate(recycle_candidates[:3]):
        day_idx = i + 1  # skip day 1 (retention slots may occupy it)
        slot_idx = day_idx * slots_per_day
        if slot_idx >= len(tasks):
            break
        cur_fmt = tasks[slot_idx].get("format") or "text"
        tasks[slot_idx] = {
            "scheduled_date": tasks[slot_idx]["scheduled_date"],
            "scheduled_time": tasks[slot_idx]["scheduled_time"],
            "format": alt.get(cur_fmt, "text"),
            "topic": f"Recycle · {cand.get('text_preview') or cand.get('text', '')[:80]}",
            "kind": "recycle",
        }


def boost_format(content_mix: list[dict], fmt: str, bump: float = 12.0) -> list[dict]:
    """Lean the mix toward `fmt` (the channel's highest-ER format) to close an ER
    gap, then renormalise to 100%. Gentle bump so it composes with the poll floor."""
    mix = {m["format"]: float(m["pct"]) for m in content_mix}
    if not mix:
        return content_mix
    mix[fmt] = mix.get(fmt, 0.0) + bump
    return _normalise_to_pct(mix)


def _weighted_format_cycle(content_mix: list[dict]) -> list[str]:
    """Expand content_mix percentages into a repeating format sequence, with the
    formats *interleaved* (not clustered) so each day gets a varied mix while the
    overall proportions still match the percentages.

    Each format's N occurrences are spread evenly across [0,1) by fractional
    position, then all occurrences are merged in position order. e.g. counts
    article=4, video=4, poll=2, link=1 -> article, video, poll, article, video,
    link, article, video, poll, article, video (so day 1 isn't all articles).
    """
    counts: dict[str, int] = {}
    for entry in content_mix:
        counts[entry["format"]] = max(1, round(entry["pct"] / 10))
    if not counts:
        return ["article"]
    spread: list[tuple[float, str]] = []
    for fmt, n in counts.items():
        for i in range(n):
            spread.append(((i + 0.5) / n, fmt))  # evenly spaced in [0,1)
    spread.sort(key=lambda x: (x[0], x[1]))      # merge by position, name tiebreak
    return [fmt for _, fmt in spread]


# ── Persistence ──────────────────────────────────────────────────────────────
_TASK_FORMATS = {"text", "photo", "video", "poll", "link", "carousel"}
# map content formats to task-format enum where they differ
_FORMAT_MAP = {"article": "text", "meme": "photo"}


async def save_strategy(channel_id: str | uuid.UUID, strategy_payload: dict) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        strat = Strategy(
            channel_id=cid,
            strategy_type=StrategyType(strategy_payload.get("strategy_type", "weekly")),
            period_start=date.fromisoformat(strategy_payload["period_start"]),
            period_end=date.fromisoformat(strategy_payload["period_end"]),
            goal=strategy_payload.get("goal"),
            post_frequency_per_day=strategy_payload.get("post_frequency_per_day"),
            content_mix=strategy_payload.get("content_mix"),
            primary_topics=strategy_payload.get("primary_topics"),
            growth_tactics=strategy_payload.get("growth_tactics"),
            analysis={
                "diagnosis": strategy_payload.get("diagnosis"),
                "benchmark": strategy_payload.get("benchmark"),
                "fatigue": strategy_payload.get("fatigue"),
            },
            status=StrategyStatus.active,
        )
        session.add(strat)
        await session.flush()
        count = 0
        for t in strategy_payload.get("tasks", []):
            fmt = _FORMAT_MAP.get(t.get("format"), t.get("format"))
            if fmt not in _TASK_FORMATS:
                fmt = "text"
            session.add(
                StrategyTask(
                    strategy_id=strat.id,
                    channel_id=cid,
                    scheduled_date=date.fromisoformat(t["scheduled_date"]),
                    scheduled_time=time.fromisoformat(t["scheduled_time"]),
                    format=fmt,
                    topic=t.get("topic"),
                    kind=t.get("kind"),
                )
            )
            count += 1
        await session.commit()
        return {"strategy_id": str(strat.id), "tasks_created": count}


async def archive_old_strategy(
    channel_id: str | uuid.UUID, strategy_type: str | None = None
) -> dict[str, Any]:
    """Mark active strategies completed; preserve approved/published tasks.

    When ``strategy_type`` is set, only archives active strategies of that type
    so a daily refresh does not wipe the weekly plan (and its pending slots).
    """
    cid = uuid.UUID(str(channel_id))
    preserved = 0
    async with AsyncSessionLocal() as session:
        q = select(Strategy).where(
            Strategy.channel_id == cid, Strategy.status == StrategyStatus.active
        )
        if strategy_type:
            q = q.where(Strategy.strategy_type == StrategyType(strategy_type))
        actives = (await session.execute(q)).scalars().all()
        for s in actives:
            s.status = StrategyStatus.completed
        if actives:
            tasks = (
                await session.execute(
                    select(StrategyTask).where(StrategyTask.channel_id == cid)
                )
            ).scalars().all()
            preserved = sum(1 for t in tasks if t.status and t.status.value in ("approved", "published"))
        await session.commit()
    return {"archived": len(actives), "tasks_preserved": preserved}


async def get_active_strategy(channel_id: str | uuid.UUID) -> dict | None:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        s = (
            await session.execute(
                select(Strategy)
                .where(Strategy.channel_id == cid, Strategy.status == StrategyStatus.active)
                .order_by(Strategy.created_at.desc())
            )
        ).scalars().first()
        if not s:
            return None
        return {
            "strategy_id": str(s.id),
            "goal": s.goal,
            "post_frequency_per_day": s.post_frequency_per_day,
            "content_mix": s.content_mix,
            "primary_topics": s.primary_topics,
        }


async def update_cron_for_content_agent(
    channel_id: str | uuid.UUID, slots: list[dict], lead_time_minutes: int = 30
) -> dict[str, Any]:
    """Register one post_slot cron per slot time, firing lead_time before posting.

    Merges times from the new plan with any still-pending tasks so a daily
    refresh does not drop weekly slot coverage.
    """
    cid = uuid.UUID(str(channel_id))
    created = 0
    exprs: set[str] = set()

    def _add_time(t: str | None) -> None:
        if not t:
            return
        hh, mm = (int(x) for x in t.split(":")[:2])
        total = (hh * 60 + mm) - lead_time_minutes
        total %= 24 * 60
        exprs.add(f"{total % 60} {total // 60} * * *")

    for s in slots:
        _add_time(s.get("scheduled_time"))

    async with AsyncSessionLocal() as session:
        pending = (
            await session.execute(
                select(StrategyTask).where(
                    StrategyTask.channel_id == cid,
                    StrategyTask.status == TaskStatus.pending,
                )
            )
        ).scalars().all()
        for t in pending:
            if t.scheduled_time:
                _add_time(t.scheduled_time.isoformat()[:5])
        # replace this channel's content-agent post-slot crons
        await session.execute(
            delete(CronJob).where(
                CronJob.channel_id == cid,
                CronJob.agent == "content_intelligence",
                CronJob.cadence_label == CadenceLabel.post_slot,
            )
        )
        for expr in exprs:
            session.add(
                CronJob(
                    channel_id=cid,
                    agent="content_intelligence",
                    cron_expression=expr,
                    cadence_label=CadenceLabel.post_slot,
                    is_active=True,
                )
            )
            created += 1
        await session.commit()
    return {"cron_jobs_created": created, "cron_jobs_updated": 0}


# ── Due-slot helpers (used by the content-slot dispatcher) ───────────────────
async def get_due_tasks(lead_minutes: int = 30) -> list[dict[str, Any]]:
    """Pending tasks whose slot is within the next `lead_minutes` (fire window).

    Slots are stored in LOCAL_TZ (audience clock), so the fire window is computed
    in that timezone too.
    """
    now = datetime.now(LOCAL_TZ)
    horizon = now + timedelta(minutes=lead_minutes)
    today = now.date()
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(StrategyTask).where(
                    StrategyTask.status == TaskStatus.pending,
                    StrategyTask.scheduled_date == today,
                )
            )
        ).scalars().all()
    due = []
    for t in rows:
        if not t.scheduled_time:
            continue
        slot_dt = datetime.combine(t.scheduled_date, t.scheduled_time, tzinfo=LOCAL_TZ)
        if now <= slot_dt <= horizon:
            due.append({"id": str(t.id), "channel_id": str(t.channel_id),
                        "scheduled_time": t.scheduled_time.isoformat()})
    return due


async def get_pending_tasks_for_channel(
    channel_id: str | uuid.UUID,
    days_ahead: int | None = None,
) -> list[dict[str, Any]]:
    """Still-pending slots for the channel's LATEST active strategy, ordered by
    slot time. Scoped to the single most-recent strategy so a coexisting
    daily+weekly plan can't double-generate.

    days_ahead: if set, only return slots whose scheduled_date is within that many
    days from today. Used for ephemeral-content channels (deals/shopping) so
    content is never generated more than N days in advance — deals expire."""
    cid = uuid.UUID(str(channel_id))
    today = datetime.now(LOCAL_TZ).date()
    cutoff = today + timedelta(days=days_ahead) if days_ahead is not None else None
    async with AsyncSessionLocal() as session:
        strat_id = (
            await session.execute(
                select(Strategy.id)
                .where(Strategy.channel_id == cid, Strategy.status == StrategyStatus.active)
                .order_by(Strategy.created_at.desc())
            )
        ).scalars().first()
        if strat_id is None:
            return []
        filters = [
            StrategyTask.strategy_id == strat_id,
            StrategyTask.status == TaskStatus.pending,
        ]
        if cutoff is not None:
            filters.append(StrategyTask.scheduled_date <= cutoff)
        rows = (
            await session.execute(
                select(StrategyTask)
                .where(*filters)
                .order_by(StrategyTask.scheduled_date.asc(), StrategyTask.scheduled_time.asc())
            )
        ).scalars().all()
    return [{"id": str(t.id), "channel_id": str(t.channel_id),
             "format": t.format.value if t.format else None,
             "kind": t.kind,
             "scheduled_date": t.scheduled_date.isoformat() if t.scheduled_date else None,
             "scheduled_time": t.scheduled_time.isoformat() if t.scheduled_time else None}
            for t in rows]


async def mark_task_generated(task_id: str | uuid.UUID, generated_post_id: str | None = None) -> None:
    tid = uuid.UUID(str(task_id))
    async with AsyncSessionLocal() as session:
        t = (await session.execute(select(StrategyTask).where(StrategyTask.id == tid))).scalar_one_or_none()
        if t:
            t.status = TaskStatus.generated
            if generated_post_id:
                t.generated_post_id = uuid.UUID(generated_post_id)
            await session.commit()


# ── Inputs loader ────────────────────────────────────────────────────────────
async def load_strategy_inputs(channel_id: str | uuid.UUID) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        channel = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()
        dna_row = (await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))).scalar_one_or_none()

        async def latest(stype):
            return (
                await session.execute(
                    select(AnalyticsSnapshot)
                    .where(AnalyticsSnapshot.channel_id == cid, AnalyticsSnapshot.snapshot_type == stype)
                    .order_by(AnalyticsSnapshot.created_at.desc())
                )
            ).scalars().first()

        daily = await latest(SnapshotType.daily)
        weekly = await latest(SnapshotType.weekly)
        # how many series posts already planned -> next day number (continuity)
        series_count = (await session.execute(
            select(func.count(StrategyTask.id))
            .where(StrategyTask.channel_id == cid, StrategyTask.kind == "series")
        )).scalar() or 0
        comps = (
            await session.execute(
                select(Competitor)
                .where(Competitor.channel_id == cid)
                .order_by(Competitor.rank.asc().nulls_last())
                .limit(5)
            )
        ).scalars().all()

    def dna_dict(d):
        if not d:
            return {}
        return {
            "post_frequency_per_day": d.post_frequency_per_day,
            "avg_er": d.avg_er,
            "top_content_formats": d.top_content_formats,
            "top_topics": d.top_topics,
            "best_post_hour": d.best_post_hour,
            "best_post_days": d.best_post_days,
            "category": d.category,
            "sub_category": d.sub_category,
        }

    def snap_dict(s):
        if not s:
            return None
        return {
            "subscriber_delta": s.subscriber_delta,
            "subscriber_delta_pct": s.subscriber_delta_pct,
            "avg_er": s.avg_er,
            "churn_signal": s.churn_signal,
        }

    # Feed the Analytics agent's measured ER-by-format into the mix computation
    er_by_format = None
    intelligence: dict = {}
    for snap in (daily, weekly):
        fe = (getattr(snap, "intelligence", None) or {}).get("format_engagement") if snap else None
        if fe:
            er_by_format = {e["label"]: e["avg_er"] for e in fe if e.get("avg_er") is not None} or None
            if er_by_format:
                break
    for snap in (daily, weekly):
        if snap and getattr(snap, "intelligence", None):
            intelligence = snap.intelligence or {}
            break

    community_state = (intelligence.get("community_signal") or {}).get("state")
    recycle_candidates = intelligence.get("recycle_candidates") or []

    return {
        "channel": {"category": channel.category, "username": channel.telegram_username} if channel else {},
        "dna": dna_dict(dna_row),
        "analytics_daily": snap_dict(daily),
        "analytics_weekly": snap_dict(weekly),
        "er_by_format": er_by_format,
        "community_state": community_state,
        "recycle_candidates": recycle_candidates,
        "series_day": series_count + 1,
        "competitors": [
            {"username": c.competitor_username, "avg_er": c.avg_er, "top_themes": c.top_content_themes}
            for c in comps
        ],
    }
