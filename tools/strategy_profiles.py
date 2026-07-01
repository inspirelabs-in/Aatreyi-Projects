"""Strategy profiles — the domain-independent strategy layer.

The Strategy Agent works the same for EVERY channel category. What differs per
niche is a *strategy profile*: the inferred posting frequency, content mix, media
mix, timing and execution rules. `infer_strategy_profile` derives that profile from
the channel's niche + audience + historical performance + competitor analysis
BEFORE any execution plan is built. The planner then materialises slots from the
profile — it never special-cases a category.

Two structural planners exist (a profile picks one):

    * ``dense``   — many posts/day spread across a window, each JIT-scraped from an
                    external source (e.g. a deals aggregator: loot + single deals).
    * ``curated`` — a few well-timed posts/day at peak audience hours, authored or
                    sourced (tech, entertainment, finance, education, sports, news…).

Adding a new category needs NO code change: an unknown category falls back to the
curated content profile, tuned by that channel's own signals. A new *structural*
behaviour (a second dense niche, say) is one entry in ``DEALS_CATEGORIES`` plus a
branch in the profile builder — the planner and executor stay untouched.
"""
from __future__ import annotations

from typing import Any

from config import settings

DENSE = "dense"
CURATED = "curated"

# Category → structural family. Only the deals family uses the dense/JIT-scraped
# planner today; every other niche uses the curated content planner. Unknown
# categories default to content, so any new niche works with no code change.
DEALS_CATEGORIES = {"deals", "shopping", "coupons", "offers"}


def category_family(category: str | None) -> str:
    """Map a channel category to its strategy family ('deals' | 'content')."""
    return "deals" if (category or "").lower().strip() in DEALS_CATEGORIES else "content"


def _media_mix_from_formats(content_mix: list[dict] | None) -> list[dict]:
    """Derive a media mix (visual vs text) from the inferred content-format mix."""
    visual = {"photo", "meme", "video", "carousel"}
    agg: dict[str, float] = {}
    for m in content_mix or []:
        bucket = "photo/video" if m.get("format") in visual else "text/link"
        agg[bucket] = agg.get(bucket, 0.0) + float(m.get("pct") or 0)
    return [{"media": k, "pct": round(v)} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]


def _scale_deal_counts(target: int) -> tuple[int, int, int, int]:
    """Scale the configured loot/single and Amazon/Flipkart splits to hit `target`
    posts/day while preserving the configured ratios. Returns
    (loot, single, single_amazon, single_flipkart)."""
    base_loot = settings.GRABON_LOOT_PER_DAY
    base_single = settings.GRABON_SINGLE_PER_DAY
    base_total = max(base_loot + base_single, 1)
    target = max(int(target), 1)
    loot = round(target * base_loot / base_total)
    loot = max(0, min(loot, target))
    single = target - loot
    # Amazon/Flipkart split of the singles, preserving the configured ratio.
    a, f = settings.GRABON_SINGLE_AMAZON, settings.GRABON_SINGLE_FLIPKART
    ratio_total = max(a + f, 1)
    amazon = round(single * a / ratio_total)
    amazon = max(0, min(amazon, single))
    flipkart = single - amazon
    return loot, single, amazon, flipkart


def _deals_profile(category: str | None, signals: dict) -> dict[str, Any]:
    """The deals-aggregator profile (GrabOn is an instance of this — NOT a special
    case). Dense JIT-scraped planner: loot compilations + single-product posts,
    marketplace-split, spread across the posting window. Counts come from config by
    default, or are scaled to the organization's configured daily target when set."""
    target = signals.get("daily_target")
    if target:
        loot, single, single_amazon, single_flipkart = _scale_deal_counts(target)
    else:
        loot = settings.GRABON_LOOT_PER_DAY
        single = settings.GRABON_SINGLE_PER_DAY
        single_amazon = settings.GRABON_SINGLE_AMAZON
        single_flipkart = settings.GRABON_SINGLE_FLIPKART
    total = max(loot + single, 1)
    start, end = settings.GRABON_POST_START_HOUR, settings.GRABON_POST_END_HOUR
    peak = sorted(signals.get("peak_hours") or [13, 20, 21])
    return {
        "category": category,
        "family": "deals",
        "planner": DENSE,
        "posts_per_day": total,
        "content_mix": [
            {"format": "link", "pct": round(loot / total * 100)},
            {"format": "photo", "pct": round(single / total * 100)},
        ],
        "media_mix": [
            {"media": "none (loot)", "pct": round(loot / total * 100)},
            {"media": "photo (single)", "pct": round(single / total * 100)},
        ],
        "timing": {"mode": "window", "window": [start, end], "peak_hours": peak,
                   "peak_source": signals.get("peak_source") or "competitor",
                   "has_peak_data": bool(signals.get("has_peak_data"))},
        "execution_rules": {
            "needs_scraping": True,
            "scrape_lead_min": settings.CONTENT_GENERATION_LEAD_MIN,
            "one_link": True,
            "dedup": True,
            "auto_publish": True,
            "kinds": {
                "loot": loot,
                "single": single,
                "marketplace_split": {
                    "Amazon": single_amazon,
                    "Flipkart": single_flipkart,
                },
            },
        },
        "rationale": (
            f"Deals-aggregator niche: the audience follows for a high volume of fresh, "
            f"deeply-discounted products, so the winning strategy is DENSE posting — "
            f"{total} posts/day across {start:02d}:00–{(end + 1) % 24 or 24:02d}:00. "
            f"{loot} loot compilations (many clickable links, no image) give breadth; "
            f"{single} single-product photo posts spotlight standout deals "
            f"(split {single_amazon} Amazon / {single_flipkart} Flipkart)"
            + (" — scaled to your organization's daily target" if target else "")
            + ". Every deal is scraped just-in-time so prices/stock are live."
        ),
    }


def _content_profile(category: str | None, signals: dict) -> dict[str, Any]:
    """The curated content profile for any non-deals niche (tech, entertainment,
    finance, education, sports, news, …). Frequency, format mix and timing are
    INFERRED from the channel's own history + competitor analysis — nothing is
    hardcoded per category, so any niche works out of the box."""
    ppd = int(signals.get("posts_per_day") or 1)
    content_mix = signals.get("content_mix") or []
    schedule_hours = signals.get("slot_hours") or []
    # Real audience peak hours (for honest "peak hour" evidence) — NOT every slot
    # hour. Falls back to the schedule hours only when no peak data exists.
    peak_hours = signals.get("peak_hours") or schedule_hours
    top_formats = ", ".join(m["format"] for m in content_mix[:3]) or "a balanced mix"
    peak_txt = ", ".join(f"{h:02d}:00" for h in schedule_hours[:3]) or "peak audience hours"
    return {
        "category": category,
        "family": "content",
        "planner": CURATED,
        "posts_per_day": ppd,
        "content_mix": content_mix,
        "media_mix": _media_mix_from_formats(content_mix),
        "timing": {"mode": "peak_hours", "peak_hours": peak_hours,
                   "peak_source": signals.get("peak_source") or "audience",
                   "has_peak_data": bool(signals.get("has_peak_data"))},
        "execution_rules": {
            "needs_scraping": False,
            "generate_lead_min": settings.CONTENT_GENERATION_LEAD_MIN,
            "one_link": True,
            "dedup": True,
            "auto_publish": True,
        },
        "rationale": (
            f"{(category or 'General').title()} niche: engagement here is driven by a few "
            f"well-crafted, well-timed posts rather than volume, so the strategy is CURATED — "
            f"{ppd} post(s)/day at {peak_txt}, leaning on {top_formats} (the formats that "
            f"perform best for this channel and its competitors). Frequency and mix are tuned "
            f"to the channel's own engagement history and competitor benchmarks."
        ),
    }


def infer_strategy_profile(category: str | None, signals: dict) -> dict[str, Any]:
    """Infer the optimal strategy profile for a channel from its niche + signals.

    `signals` carries the already-computed inference inputs (posts_per_day,
    content_mix, slot_hours, peak_hours, …). Returns a resolved profile describing
    WHAT the strategy should be (frequency, mixes, timing, execution rules) and WHY
    — this is produced BEFORE the execution plan is generated."""
    if category_family(category) == "deals":
        return _deals_profile(category, signals)
    return _content_profile(category, signals)
