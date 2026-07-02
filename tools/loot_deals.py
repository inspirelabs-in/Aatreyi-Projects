"""GrabOn auto-poster composers: loot-deal compilations + single-product deals.

A LOOT post groups several scraped deals under broad category headings, each line
a clickable affiliate link (HTML), e.g.:

    🔥🔥 Afternoon Loot Deals 🔥🔥

    ⚡ ELECTRONICS
    • boAt Airdopes 141 (90% OFF)
    • Noise Smartwatch (75% OFF)

    👕 FASHION
    • Levis Men Jeans (60% OFF)

A SINGLE post is one product (photo + affiliate button). Both use the affiliate
URLs already built by the scrapers (Amazon tag / Flipkart affid). Pure/formatting
only — scraping, publishing and scheduling live elsewhere.
"""
from __future__ import annotations

import html as _html
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import settings
from tools.content import _title_fingerprint, is_title_dupe
from tools.deal_scrapers import is_junk_title

# Greeting/time must be on the audience clock (IST), not the container's UTC —
# otherwise a 6:36 pm IST post is labelled "Afternoon" (13:06 UTC).
_LOCAL_TZ = ZoneInfo(settings.SCHEDULER_TIMEZONE)

# Broad headings (ordered) -> the scrape categories that fall under them.
LOOT_BUCKETS: list[tuple[str, set[str]]] = [
    ("⚡ ELECTRONICS",      {"Electronics", "Mobiles", "Headphones", "Appliances"}),
    ("👕 FASHION",          {"Fashion Men", "Fashion Women", "Ethnic Wear", "Sunglasses"}),
    ("👟 FOOTWEAR & BAGS",  {"Footwear", "Handbags", "Bags & Luggage"}),
    ("⌚ ACCESSORIES",      {"Watches", "Jewellery"}),
    ("💄 BEAUTY",           {"Beauty", "Makeup", "Perfumes"}),
    ("🏠 HOME & KITCHEN",   {"Home & Kitchen", "Home Decor", "Grocery"}),
    ("🧸 TOYS & SPORTS",    {"Toys & Kids", "Sports"}),
]


def greeting(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 12:
        return "Morning"
    if 12 <= h < 17:
        return "Afternoon"
    if 17 <= h < 21:
        return "Evening"
    return "Night"


def _interleave(a: list, b: list) -> list:
    """Evenly merge two lists by fractional position (e.g. 15 Amazon + 10 Flipkart
    -> spread, not clustered)."""
    seq: list[tuple[float, Any]] = []
    for i, x in enumerate(a):
        seq.append(((i + 0.5) / max(len(a), 1), x))
    for i, x in enumerate(b):
        seq.append(((i + 0.5) / max(len(b), 1), x))
    seq.sort(key=lambda t: t[0])
    return [x for _, x in seq]


def daily_plan() -> list[tuple[str, str | None]]:
    """The day's post schedule: GRABON_LOOT_PER_DAY loot + GRABON_SINGLE_PER_DAY
    single posts, interleaved; singles split Amazon/Flipkart per config."""
    n_loot = settings.GRABON_LOOT_PER_DAY
    singles = _interleave(["Amazon"] * settings.GRABON_SINGLE_AMAZON,
                          ["Flipkart"] * settings.GRABON_SINGLE_FLIPKART)
    plan: list[tuple[str, str | None]] = []
    si = 0
    total = n_loot + len(singles)
    for i in range(total):
        # alternate loot / single; once one runs out, emit the other
        want_loot = (i % 2 == 0)
        loot_left = sum(1 for t, _ in plan if t == "loot") < n_loot
        single_left = si < len(singles)
        if (want_loot and loot_left) or not single_left:
            if loot_left:
                plan.append(("loot", None))
            elif single_left:
                plan.append(("single", singles[si])); si += 1
        else:
            plan.append(("single", singles[si])); si += 1
    return plan


def _label(deal: dict, max_len: int = 60) -> str:
    """Short, human label for a loot line: clean title (trimmed at a WORD boundary
    so it never cuts mid-word) + discount."""
    title = " ".join((deal.get("title") or "").split())
    pct = deal.get("discount_pct")
    if len(title) > max_len:
        # cut at the last whole word within max_len, then add an ellipsis
        title = title[:max_len].rsplit(" ", 1)[0].rstrip(" -–|,·") + "…"
    return f"{title} ({pct}% OFF)" if pct else title


def build_loot_post(
    deals: list[dict], seen: list[frozenset], recent_urls: set[str] | None = None
) -> dict | None:
    """Compose a loot post from the deal pool, grouped by bucket, skipping products
    already posted recently (``seen`` title fingerprints + ``recent_urls`` product
    links). Returns {post_text(HTML), used} or None if too few fresh deals."""
    now = datetime.now(_LOCAL_TZ)
    used_fps = list(seen)
    recent = recent_urls or set()
    seen_urls: set[str] = set()      # no repeated product link within the post
    seen_labels: set[str] = set()    # no two identical-looking lines ("Dervin (80% OFF)")
    sections: list[str] = []
    used: list[dict] = []
    for heading, cats in LOOT_BUCKETS:
        if len(sections) >= settings.GRABON_LOOT_BUCKETS:
            break
        lines: list[str] = []
        for d in deals:
            if len(lines) >= settings.GRABON_LOOT_PER_BUCKET:
                break
            if (d.get("category") not in cats):
                continue
            url = (d.get("affiliate_url") or d.get("product_url") or "").strip()
            if not url:
                continue
            # Dedup by URL (within post AND across recent posts), by visible label,
            # and by title — so the same product/link never repeats. The label guard
            # is key because scraped titles are often just a brand ("Dervin"), which
            # the fingerprint dedup can't judge, making two lines look identical.
            uk = url.split("?")[0].rstrip("/").lower()
            if uk in seen_urls or uk in recent:
                continue
            if is_junk_title(d.get("title")):
                continue
            label = _label(d)
            label_key = label.lower()
            if label_key in seen_labels:
                continue
            if is_title_dupe(d.get("title"), used_fps):
                continue
            lines.append(f'• <a href="{_html.escape(url, quote=True)}">{_html.escape(label)}</a>')
            used.append(d)
            seen_urls.add(uk)
            seen_labels.add(label_key)
            used_fps.append(_title_fingerprint(d.get("title")))
        if lines:
            sections.append(f"<b>{heading}</b>\n" + "\n".join(lines))
    # Post is worthwhile with EITHER one category or many — a single full bucket
    # (>=3 links) is enough. Only bail when there's essentially nothing to show.
    if len(sections) < 1 or len(used) < 3:
        return None
    text = f"🔥🔥 {greeting(now)} Loot Deals 🔥🔥\n\n" + "\n\n".join(sections)
    text += "\n\n🛍️ Tap any item to grab the deal!"
    return {"post_text": text, "post_format": "text", "parse_mode": "HTML", "used": used}


def build_single_deal_post(
    deals: list[dict], platform: str, seen: list[frozenset],
    prefer_ranked: bool = False, recent_urls: set[str] | None = None,
) -> dict | None:
    """Pick the best fresh single-product deal for ``platform`` and compose a
    photo post with an affiliate button. None if no fresh deal.

    When ``prefer_ranked`` is set, ``deals`` is assumed already sorted best-first
    (by the executor's ranker: discount + engagement + trend + stock) and the
    incoming order is honoured instead of re-sorting by raw discount."""
    recent = recent_urls or set()
    def _fresh_url(d: dict) -> bool:
        u = (d.get("affiliate_url") or d.get("product_url") or "").split("?")[0].rstrip("/").lower()
        return bool(u) and u not in recent
    cands = [d for d in deals
             if (d.get("platform") == platform)
             and _fresh_url(d)
             and not is_junk_title(d.get("title"))
             and not is_title_dupe(d.get("title"), seen)]
    if not cands:
        return None
    if not prefer_ranked:
        cands.sort(key=lambda d: d.get("discount_pct") or 0, reverse=True)
    d = cands[0]
    title = " ".join((d.get("title") or "").split())
    pct = d.get("discount_pct")
    cur = d.get("current_price")
    orig = d.get("original_price")
    price_bit = f"{cur}" + (f" (was {orig})" if orig else "")
    head = f"🔥 {title}"
    body = f"{head}\n\n💸 {price_bit}" + (f"  •  {pct}% OFF" if pct else "")
    url = (d.get("affiliate_url") or d.get("product_url") or "").strip()
    return {
        "post_text": body,
        "post_format": "photo" if d.get("image_url") else "text",
        "media_url": d.get("image_url"),
        "link_url": url,
        "cta": "🛒 Grab Deal",
        "used": [d],
    }
