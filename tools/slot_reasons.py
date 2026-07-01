"""Evidence-based, sequential slot reasoning.

The Strategy Agent does NOT explain slots with generic filler ("high engagement",
"trending", "best time"). It reasons SEQUENTIALLY with decision memory: while
building the plan it remembers every slot already scheduled, and each slot's reason
is an Evidence→Decision derived from the real signals that caused the choice:

    • category engagement rank (from the channel's category analysis)
    • diversity spacing (how long since this category / marketplace was used)
    • marketplace allocation vs the daily target
    • audience / competitor peak hours (only when that data actually exists)
    • recent competitor trend (only when the category is actually trending)
    • loot vs single balance against the daily targets

`_apply_slot_reasons` runs one sequential pass over the plan: it assigns each
open slot's category (respecting diversity + rank) and writes a unique reason that
references the prior scheduling decisions. Because every reason is built from live
per-slot state, no two slots read the same.
"""
from __future__ import annotations

from typing import Any

RETENTION_KINDS = {"reengage", "series", "weekly", "challenge", "recycle"}


def _hh(slot: dict) -> int:
    try:
        return int(str(slot.get("scheduled_time") or "0")[:2])
    except Exception:
        return 0


def _hhmm(slot: dict) -> str:
    return str(slot.get("scheduled_time") or "")[:5]


def _mins_between(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        (h1, m1), (h2, m2) = [x.split(":")[:2] for x in (a, b)]
        return abs((int(h2) * 60 + int(m2)) - (int(h1) * 60 + int(m1)))
    except Exception:
        return None


def _hour_evidence(hh: int, ctx: dict) -> str | None:
    """Peak-hour evidence — ONLY when real hour data exists (never a generic claim)."""
    if not ctx.get("has_peak_data") or hh not in ctx.get("peak_hours", set()):
        return None
    if ctx.get("peak_source") == "audience":
        return f"{hh:02d}:00 is a peak audience-activity hour in your hourly engagement data."
    return f"{hh:02d}:00 is a top posting hour for your competitors."


def _choose_category(ctx: dict, state: dict, pos: int):
    """Pick the highest-engagement-ranked category not used within the diversity
    window; return (category, rank_index, skipped) where skipped lists higher-ranked
    categories deferred for diversity (with how many slots ago they ran)."""
    ranked = ctx["ranked"]
    n = len(ranked)
    window = min(max(n - 1, 1), ctx.get("diversity_window", 4))
    last_pos = state["cat_last_pos"]
    skipped = []
    for r, cat in enumerate(ranked):
        lp = last_pos.get(cat)
        if lp is None or (pos - lp) > window:
            return cat, r, skipped
        skipped.append((cat, pos - lp))
    return ranked[0], 0, skipped  # everything used recently → fall back to the best


def _assemble(evidence: list[str], decision: str) -> str:
    ev = [e for e in evidence if e][:4]
    body = "Evidence:\n" + "\n".join(f"• {e}" for e in ev)
    return f"{body}\nDecision: {decision}"


def _deal_slot(slot: dict, ctx: dict, state: dict, pos: int) -> str:
    hh = _hh(slot)
    tstr = _hhmm(slot)
    kind = (slot.get("kind") or "single").lower()
    ranked = ctx["ranked"]
    n = len(ranked)

    if kind == "loot":
        state["loot_seen"] += 1
        ev = []
        cats = ", ".join(ranked[:3]) if ranked else "your top categories"
        ev.append(f"Bundles your top-ranked categories ({cats}) into one high-density post.")
        lt = ctx.get("loot_target")
        ev.append(f"Loot allocation: {state['loot_seen']}/{lt} loot posts today."
                  if lt else f"Loot post #{state['loot_seen']} today.")
        h = _hour_evidence(hh, ctx)
        if h:
            ev.append(h)
        slot["topic"] = "Multiple"
        return _assemble(ev, "Aggregate multiple live deals as a clickable link-list (no image) for breadth.")

    # single-product slot: choose the category with rank + diversity memory
    state["single_seen"] += 1
    cat, rank_idx, skipped = _choose_category(ctx, state, pos)
    slot["topic"] = cat
    ev = []
    if n:
        ev.append(f"{cat} ranks #{rank_idx + 1} of {n} by engagement in your category analysis.")
    last_t = state["cat_last_time"].get(cat)
    if last_t is None:
        ev.append(f"No {cat} post scheduled yet today — broadens category coverage.")
    else:
        mins = _mins_between(last_t, tstr)
        ev.append(f"{cat} last scheduled {mins} min ago; spacing keeps the feed diverse."
                  if mins is not None else f"{cat} re-used after a gap for balance.")
    if skipped:
        sc, slots_ago = skipped[0]
        ev.append(f"{sc} skipped — used {slots_ago} slot(s) ago (diversity rule).")
    mp = slot.get("marketplace")
    if mp:
        state["mp_count"][mp] = state["mp_count"].get(mp, 0) + 1
        tgt = (ctx.get("marketplace_targets") or {}).get(mp)
        if state["mp_last"] and state["mp_last"] != mp:
            ev.append(f"Switched to {mp} to avoid consecutive {state['mp_last']} posts.")
        else:
            ev.append(f"{mp} allocation: {state['mp_count'][mp]}/{tgt} today."
                      if tgt else f"{mp} selected per the marketplace plan.")
        state["mp_last"] = mp
    h = _hour_evidence(hh, ctx)
    if h:
        ev.append(h)
    if cat.lower() in ctx.get("trending", set()):
        ev.append(f"{cat} is rising in competitor posting this week.")
    decision = f"Schedule {cat} from {mp or 'the marketplace'} as a single-product photo post."
    state["cat_last_pos"][cat] = pos
    state["cat_last_time"][cat] = tstr
    return _assemble(ev, decision)


_NICHE_DECISION = {
    "financ": "before market hours to maximise relevance",
    "stock": "before market hours to maximise relevance",
    "crypto": "around active trading hours",
    "entertain": "in the evening visual-content window",
    "movie": "in the evening visual-content window",
    "tech": "in the tech audience's active window",
    "edu": "during study hours",
    "sport": "around match-day activity",
    "news": "at a high-traffic news-checking hour",
    "gam": "in peak gaming hours",
    "health": "in the morning planning window",
}


def _niche_decision_hint(niche: str) -> str:
    n = (niche or "").lower()
    for k, v in _NICHE_DECISION.items():
        if k in n:
            return v
    return "at a peak audience-activity window"


def _content_slot(slot: dict, ctx: dict, state: dict, pos: int) -> str:
    hh = _hh(slot)
    tstr = _hhmm(slot)
    niche = ctx.get("niche") or "channel"
    fmt = (slot.get("format") or "post").lower()
    kind = (slot.get("kind") or "").lower()

    if kind in RETENTION_KINDS:
        topic = slot.get("topic") or "the audience"
        ev = []
        reason_by_kind = {
            "reengage": "Engagement/activity has dipped — a re-engagement trigger is scheduled to win back quiet members.",
            "series": f"Continues an established series on {topic} to build a return habit.",
            "weekly": f"Recurring weekly anchor so members expect fresh {niche} content on schedule.",
            "challenge": "Interactive challenge scheduled to lift participation.",
            "recycle": f"Re-uses a proven high-performer on {topic} in a new format.",
        }
        ev.append(reason_by_kind.get(kind, "Retention trigger scheduled."))
        h = _hour_evidence(hh, ctx)
        if h:
            ev.append(h)
        return _assemble(ev, f"Publish the {kind} trigger as a {fmt} at {tstr}.")

    ranked = ctx["ranked"]
    n = len(ranked)
    if ranked:
        cat, rank_idx, skipped = _choose_category(ctx, state, pos)
        slot["topic"] = cat
    else:
        cat, rank_idx, skipped = (slot.get("topic") or "general"), 0, []
    ev = []
    if n:
        ev.append(f"{cat} ranks #{rank_idx + 1} of {n} by engagement in your topic analysis.")
    last_t = state["cat_last_time"].get(cat)
    if last_t is not None:
        mins = _mins_between(last_t, tstr)
        if mins is not None:
            ev.append(f"{cat} last covered {mins} min ago; rotated for topic diversity.")
    elif skipped:
        sc, slots_ago = skipped[0]
        ev.append(f"{sc} skipped — used {slots_ago} slot(s) ago (diversity rule).")
    h = _hour_evidence(hh, ctx)
    if h:
        ev.append(h)
    state["cat_last_pos"][cat] = pos
    state["cat_last_time"][cat] = tstr
    decision = f"Publish a {fmt} on {cat} {_niche_decision_hint(niche)} ({tstr})."
    return _assemble(ev, decision)


def reason_ctx(profile: dict, ranked: list[str], trending, niche: str | None) -> dict:
    """Build the reasoning context from a resolved strategy profile."""
    profile = profile or {}
    timing = profile.get("timing") or {}
    rules = profile.get("execution_rules") or {}
    kinds = rules.get("kinds") or {}
    return {
        "family": profile.get("family"),
        "niche": niche or profile.get("category") or "",
        "ranked": [c for c in (ranked or []) if c],
        "trending": {str(c).lower() for c in (trending or [])},
        "peak_hours": {int(h) for h in (timing.get("peak_hours") or []) if str(h).isdigit()},
        "peak_source": timing.get("peak_source") or "competitor",
        "has_peak_data": bool(timing.get("has_peak_data")),
        "marketplace_targets": kinds.get("marketplace_split") or {},
        "loot_target": kinds.get("loot"),
        "single_target": kinds.get("single") or profile.get("posts_per_day"),
        "diversity_window": 4,
    }


def _apply_slot_reasons(tasks: list[dict[str, Any]], ctx: dict) -> None:
    """One sequential pass over the plan: assign each open slot's category with
    decision memory and stamp a unique Evidence→Decision reason. Mutates tasks."""
    state = {
        "cat_last_pos": {}, "cat_last_time": {}, "mp_count": {}, "mp_last": None,
        "loot_seen": 0, "single_seen": 0,
    }
    is_deals = ctx.get("family") == "deals"
    for pos, slot in enumerate(tasks):
        reason = _deal_slot(slot, ctx, state, pos) if is_deals else _content_slot(slot, ctx, state, pos)
        slot["rationale"] = reason
        slot["reason"] = reason
