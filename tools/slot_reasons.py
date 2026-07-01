"""Per-slot reason generation.

Growth & retention optimizations are not shown as generic advice — they are baked
into the schedule. Every execution slot carries a concise, SPECIFIC reason that
explains why it was created, referencing the factors that actually drove it:
historical engagement, competitor posting patterns, audience activity, trending
topics, category/marketplace performance, media-format choice, content diversity
and growth objectives.

Reasons are niche-aware (deals, technology, finance, entertainment, education,
sports, news, …) and rotated by slot index so the same sentence is never repeated
back-to-back. `_apply_slot_reasons` stamps every slot in a plan.
"""
from __future__ import annotations

from typing import Any


def _hour_of(slot: dict) -> int:
    t = slot.get("scheduled_time") or "00:00"
    try:
        return int(str(t).split(":")[0])
    except Exception:
        return 0


def _pick(options: list[str], index: int) -> str:
    return options[index % len(options)] if options else ""


def _tod(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


# ── Deals (dense) ────────────────────────────────────────────────────────────
_DEAL_TOD_FRAG = {
    "morning": ["Morning shoppers browse deals before the day starts",
                "Early slot catches commuters checking for discounts"],
    "afternoon": ["Midday break is a high deal-browsing window",
                  "Afternoon lull drives strong deal discovery"],
    "evening": ["Evening is peak shopping-intent time",
                "Post-work hours convert browsers into buyers"],
    "night": ["Late-night deal hunters convert well on limited-time drops",
              "Night owls actively hunt flash discounts"],
}
_LOOT_BODY = [
    "Bundles the day's biggest discounts across {cats} for breadth",
    "A scannable multi-deal drop so members catch the top discounts at a glance",
    "Aggregates high-discount finds across {cats} to widen reach",
]
_LOOT_MEDIA = "Link-list format (no image) packs many deals into one post."
_SINGLE_CAT_HOT = ["{cat} is trending among competitors right now",
                   "{cat} deals are spiking in competitor engagement"]
_SINGLE_CAT_STD = ["{cat} consistently delivers high engagement",
                   "{cat} is a top-performing category for this audience",
                   "{cat} historically drives strong click-through"]
_SINGLE_MEDIA = ["Photo format — single-product images outperform plain links",
                 "Photo chosen for higher stopping power on one hero product"]
_SINGLE_MP = ["{mp} offers the deepest discounts in {cat}",
              "{mp}'s catalogue performs strongest here"]


def _deal_reason(slot: dict, ctx: dict, index: int) -> str:
    hour = _hour_of(slot)
    is_peak = hour in ctx.get("peak_hours", set())
    trending = ctx.get("trending", set())
    kind = (slot.get("kind") or "single").lower()

    if is_peak:
        time_frag = f"Scheduled during competitor peak activity ({hour:02d}:00)"
    else:
        time_frag = _pick(_DEAL_TOD_FRAG[_tod(hour)], index)

    if kind == "loot":
        cats = ", ".join((ctx.get("cats_sample") or ["top categories"])[:3])
        body = _pick(_LOOT_BODY, index).format(cats=cats)
        parts = [time_frag, body, _LOOT_MEDIA]
    else:
        cat = slot.get("topic") or "This category"
        mp = slot.get("marketplace")
        hot = cat.lower() in trending
        cat_frag = _pick(_SINGLE_CAT_HOT if hot else _SINGLE_CAT_STD, index).format(cat=cat)
        media_frag = _pick(_SINGLE_MEDIA, index)
        parts = [time_frag, cat_frag, media_frag]
        # rotate in a marketplace / diversity note so reasons stay varied
        if mp and index % 2 == 0:
            parts[2] = _pick(_SINGLE_MP, index).format(mp=mp, cat=cat)
            parts.append("Photo format for a single hero product")
        elif index % 3 == 2:
            parts.append("Category rotated to avoid back-to-back repetition")
    return ". ".join(p.rstrip(".") for p in parts if p) + "."


# ── Content (curated) niches ─────────────────────────────────────────────────
_RETENTION = {
    "reengage": ["Re-engagement poll to win back quiet members and lift reach",
                 "A low-effort poll to re-activate lapsed members"],
    "series": ["Part of a recurring series on {topic} to build a viewing habit",
               "Next installment in the {topic} series — habit-forming cadence"],
    "weekly": ["Weekly anchor post so members expect fresh {niche} content",
               "Recurring weekly slot that trains the audience to check back"],
    "challenge": ["Interactive challenge to spark participation and comments",
                  "Community challenge to drive active engagement"],
    "recycle": ["Refreshes a past high-performer on {topic} in a new format",
                "Reworks a proven {topic} post to recapture engagement"],
}


def _niche_has(niche: str, keywords: tuple[str, ...]) -> bool:
    """Match niche keywords: 2-char tokens (e.g. 'ai', 'tv') must be a whole word so
    'ai' doesn't spuriously match 'entertAInment'; longer keywords/stems match as
    substrings (e.g. 'edu' → 'education', 'financ' → 'finance'/'financial')."""
    import re

    n = niche.lower()
    toks = set(re.findall(r"[a-z]+", n))
    for k in keywords:
        if len(k) <= 2:
            if k in toks:
                return True
        elif k in n:
            return True
    return False


def _niche_time_frag(niche: str, hour: int, is_peak: bool, index: int) -> str:
    if _niche_has(niche, ("financ", "stock", "invest", "crypto", "trading", "market", "mutual")):
        if hour < 10:
            return "Scheduled before market open for maximum relevance"
        if hour < 16:
            return "Timed to intraday market activity"
        return "Posted around market close as investors review the day"
    if _niche_has(niche, ("entertain", "movie", "film", "music", "celeb", "tv", "show", "trailer")):
        return ("Evening is peak for short-form visual entertainment" if hour >= 17
                else "Timed to daytime entertainment browsing")
    if _niche_has(niche, ("tech", "ai", "software", "coding", "developer", "startup", "gpu")):
        return _pick(["Audience engagement peaks at this hour for tech readers",
                      "Tech audience is most active in this window"], index)
    if _niche_has(niche, ("edu", "learn", "study", "exam", "course")):
        return _pick(["Scheduled when learners are most active",
                      "Study-hour slot when the audience is in learning mode"], index)
    if _niche_has(niche, ("sport", "cricket", "football", "match")):
        return "Timed around audience match-day activity"
    if _niche_has(niche, ("news", "politic")):
        return "Posted at a high-traffic news-checking hour"
    if _niche_has(niche, ("gam", "esport")):
        return "Aligned with peak gaming-audience hours"
    if _niche_has(niche, ("health", "fitness", "wellness", "yoga")):
        return ("Morning slot when health-minded readers plan their day" if hour < 12
                else "Timed to when wellness readers wind down")
    return (f"Scheduled at {hour:02d}:00, a peak audience-activity window" if is_peak
            else f"Posted at {hour:02d}:00 to match audience activity")


_FMT_FRAG = {
    "poll": ["Poll format lifts interaction and reach", "Poll to convert silent viewers into engagement"],
    "article": ["Long-form article suits in-depth {niche} readers", "Article format for depth this niche rewards"],
    "video": ["Video drives the strongest engagement here", "Short video for the highest stopping power"],
    "photo": ["Visual post for higher stopping power", "Image-led post to boost scroll-stopping reach"],
    "meme": ["Meme format for shareability and reach", "Light visual to spark shares"],
    "link": ["Curated link to a high-value external piece", "Link post to a standout resource"],
    "text": ["Concise text update for quick consumption", "Short text hit for fast reads"],
}


def _content_reason(slot: dict, ctx: dict, index: int) -> str:
    hour = _hour_of(slot)
    is_peak = hour in ctx.get("peak_hours", set())
    niche = (ctx.get("niche") or "general").lower()
    trending = ctx.get("trending", set())
    topic = slot.get("topic") or "This topic"
    fmt = (slot.get("format") or "text").lower()
    kind = (slot.get("kind") or "").lower()

    if kind in _RETENTION:
        frag = _pick(_RETENTION[kind], index).format(topic=topic, niche=niche)
        return f"{frag}. {_niche_time_frag(niche, hour, is_peak, index)}."

    time_frag = _niche_time_frag(niche, hour, is_peak, index)
    if topic.lower() in trending:
        topic_frag = f"{topic} is trending among competitors"
    else:
        topic_frag = _pick([f"{topic} is one of your best-engagement themes",
                            f"{topic} performs well for this audience"], index)
    fmt_frag = _pick(_FMT_FRAG.get(fmt, _FMT_FRAG["text"]), index).format(niche=niche)
    # vary order by index so consecutive slots read differently
    parts = [topic_frag, time_frag, fmt_frag] if index % 2 else [time_frag, topic_frag, fmt_frag]
    return ". ".join(p.rstrip(".") for p in parts if p) + "."


def build_slot_reason(slot: dict, ctx: dict, index: int) -> str:
    """Compose a concise, specific, niche-aware reason for one execution slot."""
    if ctx.get("family") == "deals":
        return _deal_reason(slot, ctx, index)
    return _content_reason(slot, ctx, index)


def _apply_slot_reasons(tasks: list[dict[str, Any]], ctx: dict) -> None:
    """Stamp every slot in a plan with its specific reason (in place). Uses the
    slot index for phrasing variety so reasons are never repeated back-to-back."""
    for i, slot in enumerate(tasks):
        reason = build_slot_reason(slot, ctx, i)
        slot["rationale"] = reason
        slot["reason"] = reason  # mirror for any consumer reading either key
