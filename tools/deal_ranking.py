"""Deal ranking for the execution scheduler.

Given a pool of freshly-scraped deals, score each one so the executor can pick the
best candidate for a slot. Signals (per the spec):

    * discount            — bigger genuine discount ranks higher
    * historical engagement — category-level: categories the audience/competitors
                              engage with most (ordered preferred list) rank higher
    * stock availability  — best-effort: a live scraped listing is treated as
                              in-stock; the executor does a quick reachability check
                              on the chosen candidate and falls to the next if dead
    * competitor trends   — categories trending among competitors get a boost

Bogus discounts (mis-parsed original prices, e.g. "₹145 (was ₹9667) • 99% OFF")
are dropped before scoring via a sanity cap.
"""
from __future__ import annotations

import re
from typing import Any

from config import settings

# Weights (sum ≈ 1.0). Discount dominates; engagement + trend refine; image is a
# small quality signal (a card with a photo is a healthier listing).
_W_DISCOUNT = 0.50
_W_ENGAGEMENT = 0.25
_W_TREND = 0.15
_W_IMAGE = 0.10


def _price_int(s: Any) -> int | None:
    if s is None:
        return None
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None


def is_plausible_discount(deal: dict) -> bool:
    """Drop deals whose discount is almost certainly a scrape error.

    Caps at DEAL_MAX_DISCOUNT (default 95%) and rejects an original/current price
    ratio above ~25x (e.g. ₹145 marked down from ₹9667) — the classic mis-parse
    where the "original" price is actually a different product's MRP on the card.
    """
    pct = deal.get("discount_pct") or 0
    cap = getattr(settings, "DEAL_MAX_DISCOUNT", 95)
    if pct > cap:
        return False
    cur, orig = _price_int(deal.get("current_price")), _price_int(deal.get("original_price"))
    if cur and orig and cur > 0 and orig / cur > 25:
        return False
    return True


def score_deal(
    deal: dict,
    preferred_categories: list[str] | None,
    trending_categories: set[str] | None,
) -> float:
    pct = min(100, max(0, deal.get("discount_pct") or 0))
    discount = pct / 100.0

    cat = (deal.get("category") or "").lower()
    prefs = [c.lower() for c in (preferred_categories or [])]
    if cat in prefs:
        # earlier in the preferred list (higher engagement) → closer to 1.0
        engagement = 1.0 - (prefs.index(cat) / max(len(prefs), 1))
    else:
        engagement = 0.3  # unknown category: neutral-low

    trends = {c.lower() for c in (trending_categories or set())}
    trend = 1.0 if cat in trends else 0.0

    image = 1.0 if deal.get("image_url") else 0.0

    return round(
        _W_DISCOUNT * discount + _W_ENGAGEMENT * engagement
        + _W_TREND * trend + _W_IMAGE * image,
        4,
    )


def rank_deals(
    deals: list[dict],
    *,
    preferred_categories: list[str] | None = None,
    trending_categories: set[str] | None = None,
    platform: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """Return deals sorted best-first, after dropping bogus discounts.

    Optional `platform` / `category` filters narrow the pool to a slot's assignment
    before ranking. Each returned deal carries a `_score` for transparency.
    """
    pool = [d for d in (deals or []) if is_plausible_discount(d)]
    if platform:
        pool = [d for d in pool if (d.get("platform") == platform)]
    if category:
        cl = category.lower()
        pool = [d for d in pool if (d.get("category") or "").lower() == cl] or pool
    for d in pool:
        d["_score"] = score_deal(d, preferred_categories, trending_categories)
    pool.sort(key=lambda d: d.get("_score") or 0, reverse=True)
    return pool


# HTTP codes that mean the product page is genuinely GONE (drop the link). Amazon
# and Flipkart routinely answer 403/429/503 to non-browser GETs (anti-bot walls),
# so those must NOT be read as "dead" — the deal was just scraped from a live
# search page, so best-effort treats it as in-stock unless the page is truly gone.
_DEAD_CODES = {404, 410}


async def is_reachable(url: str, timeout: float = 6.0) -> bool:
    """Best-effort liveness check: only a definitive 404/410 marks a link dead.

    Fail-open on anti-bot walls (403/429/503), redirects, and any network hiccup —
    the deal was already confirmed live by the Playwright scrape moments earlier,
    so this only weeds out links that have since 404'd."""
    if not url:
        return False
    try:
        import httpx

        from tools.content import _scraper_httpx_kwargs  # proxy/UA if configured

        try:
            kwargs = _scraper_httpx_kwargs() or {}
        except Exception:
            kwargs = {}
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, **kwargs) as client:
            r = await client.get(url, headers={"User-Agent": _UA_BROWSER})
            return r.status_code not in _DEAD_CODES
    except Exception:
        return True  # fail-open


_UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
