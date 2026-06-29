"""Live deal scrapers for deals-aggregator channels (e.g. GrabOn).

Replicates the manual workflow — pull today's discounted products from Amazon
India and Flipkart, wrap them in affiliate links, and hand them to the content
generator as ready-to-post items.

Discount policy (see config):
    * PREFER deals at >= DEAL_PREFERRED_DISCOUNT (default 80%).
    * If none that high, FALL BACK down to DEAL_MIN_DISCOUNT (default 65%).
    * NEVER return a deal below DEAL_MIN_DISCOUNT.

Only *current* search results are scraped (sorted by discount), so these are
"today's deals". Reposting is prevented by the content agent's existing
external_url de-dup.

NOTE: Amazon/Flipkart aggressively block datacenter IPs. From a residential IP
(local run) these scrapers work; from a cloud host they may be blocked/captcha'd,
in which case the caller falls back to grabon.in coupon pages. Requires Playwright
Chromium (`python -m playwright install chromium`).
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from config import settings

# Short-lived cache so a daily batch (many slots generated back-to-back) scrapes
# the marketplaces ONCE rather than per-slot — faster and far less likely to trip
# bot-blocking. Keyed by the scrape parameters.
_DEAL_CACHE: dict[str, Any] = {"key": None, "deals": None, "ts": 0.0}
_DEAL_CACHE_TTL_SEC = 1800  # 30 min

# ── Categories (comprehensive) ───────────────────────────────────────────────
# Amazon needs (search keyword, search index `i`); Flipkart needs a keyword.
DEAL_CATEGORIES: list[dict[str, str]] = [
    {"category": "Electronics",    "amazon_kw": "electronics",        "amazon_i": "electronics", "flipkart_kw": "electronics"},
    {"category": "Mobiles",        "amazon_kw": "smartphones",        "amazon_i": "electronics", "flipkart_kw": "mobiles"},
    {"category": "Headphones",     "amazon_kw": "headphones earbuds", "amazon_i": "electronics", "flipkart_kw": "headphones"},
    {"category": "Fashion Men",    "amazon_kw": "mens clothing",      "amazon_i": "apparel",     "flipkart_kw": "mens fashion"},
    {"category": "Fashion Women",  "amazon_kw": "womens clothing",    "amazon_i": "apparel",     "flipkart_kw": "womens clothing"},
    {"category": "Ethnic Wear",    "amazon_kw": "women kurta saree",  "amazon_i": "apparel",     "flipkart_kw": "kurtas ethnic wear"},
    {"category": "Footwear",       "amazon_kw": "shoes",              "amazon_i": "shoes",       "flipkart_kw": "footwear"},
    {"category": "Handbags",       "amazon_kw": "handbags women",     "amazon_i": "shoes",       "flipkart_kw": "handbags"},
    {"category": "Bags & Luggage", "amazon_kw": "backpacks luggage",  "amazon_i": "luggage",     "flipkart_kw": "bags"},
    {"category": "Watches",        "amazon_kw": "watches",            "amazon_i": "watches",     "flipkart_kw": "watches"},
    {"category": "Sunglasses",     "amazon_kw": "sunglasses",         "amazon_i": "apparel",     "flipkart_kw": "sunglasses"},
    {"category": "Jewellery",      "amazon_kw": "jewellery women",    "amazon_i": "apparel",     "flipkart_kw": "jewellery"},
    {"category": "Beauty",         "amazon_kw": "beauty products",    "amazon_i": "beauty",      "flipkart_kw": "beauty"},
    {"category": "Makeup",         "amazon_kw": "makeup cosmetics",   "amazon_i": "beauty",      "flipkart_kw": "makeup cosmetics"},
    {"category": "Perfumes",       "amazon_kw": "perfume deodorant",  "amazon_i": "beauty",      "flipkart_kw": "perfumes"},
    {"category": "Home & Kitchen", "amazon_kw": "home kitchen",       "amazon_i": "kitchen",     "flipkart_kw": "home kitchen"},
    {"category": "Home Decor",     "amazon_kw": "home decor",         "amazon_i": "kitchen",     "flipkart_kw": "home decor"},
    {"category": "Appliances",     "amazon_kw": "home appliances",    "amazon_i": "appliances",  "flipkart_kw": "appliances"},
    {"category": "Sports",         "amazon_kw": "sports fitness",     "amazon_i": "sporting",    "flipkart_kw": "sports fitness"},
    {"category": "Toys & Kids",    "amazon_kw": "toys games kids",    "amazon_i": "toys",        "flipkart_kw": "toys kids"},
    {"category": "Grocery",        "amazon_kw": "grocery gourmet",    "amazon_i": "grocery",     "flipkart_kw": "grocery"},
]


def resolve_deal_categories(name: str | None) -> list[dict[str, str]]:
    """Map a strategy slot's category label onto DEAL_CATEGORIES entries.

    The strategy assigns a broad category per slot (e.g. "Fashion Women",
    "Headphones"); this finds the matching scrape config so the slot pulls deals
    from THAT category. Returns [] when there's no confident match (caller then
    scrapes the full category set as a fallback)."""
    if not name:
        return []
    n = name.strip().lower()
    exact = [c for c in DEAL_CATEGORIES if c["category"].lower() == n]
    if exact:
        return exact
    # substring either direction, then keyword overlap
    subs = [c for c in DEAL_CATEGORIES
            if c["category"].lower() in n or n in c["category"].lower()
            or n in c["amazon_kw"].lower() or n in c["flipkart_kw"].lower()]
    if subs:
        return subs
    import re as _re
    n_tok = {w for w in _re.findall(r"[a-z0-9]+", n) if len(w) > 2}
    scored = []
    for c in DEAL_CATEGORIES:
        hay = f"{c['category']} {c['amazon_kw']} {c['flipkart_kw']}".lower()
        c_tok = {w for w in _re.findall(r"[a-z0-9]+", hay) if len(w) > 2}
        ov = len(n_tok & c_tok)
        if ov:
            scored.append((ov, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:1]]

# Amazon India discount filter nodes (rh=p_n_pct-off-with-tax:<node>).
# We scrape the 60%+ node (broad) and apply the 80%/65% policy in Python.
_AMAZON_NODE_60 = "2665394031"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ── Affiliate links ───────────────────────────────────────────────────────────
# Amazon ASIN = 10-char alphanumeric product id, found after /dp/, /gp/product/, etc.
_AMAZON_ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|d|product)/([A-Z0-9]{10})", re.IGNORECASE)


def _amazon_asin(url: str) -> str | None:
    """Pull the ASIN out of any Amazon product URL.

    e.g. https://www.amazon.in/AYSIS-.../dp/B0H416WF2T?ref=...&th=1  ->  B0H416WF2T
    """
    if not url:
        return None
    m = _AMAZON_ASIN_RE.search(url)
    if m:
        return m.group(1).upper()
    # Fallback: a bare 10-char ASIN sitting as its own path segment.
    m = re.search(r"/([A-Z0-9]{10})(?:[/?]|$)", url)
    return m.group(1).upper() if m else None


def build_affiliate_link(product_url: str, platform: str) -> str:
    """Wrap a scraped product URL in our affiliate link.

    Amazon   -> https://www.amazon.in/dp/<ASIN>/?tag=<AMAZON_AFFILIATE_TAG>
                (extract the ASIN after /dp/; drop the rest of the original URL)
    Flipkart -> <product-path>?<FLIPKART_AFFILIATE_PARAMS>
                (strip the product's own ?pid=...&lid=... query, then append ours)
    """
    if not product_url:
        return product_url
    is_amazon = platform == "Amazon" or "amazon." in product_url
    is_flipkart = platform == "Flipkart" or "flipkart.com" in product_url

    if is_amazon:
        tag = settings.AMAZON_AFFILIATE_TAG
        asin = _amazon_asin(product_url)
        if asin:
            link = f"https://www.amazon.in/dp/{asin}/"
            return f"{link}?tag={tag}" if tag else link
        # ASIN not found: tag the cleaned URL as-is rather than dropping the link.
        base = product_url.split("?")[0].rstrip("/")
        return f"{base}/?tag={tag}" if tag else base

    if is_flipkart:
        base = product_url.split("?")[0].rstrip("/")  # remove everything from '?' on
        params = settings.FLIPKART_AFFILIATE_PARAMS
        return f"{base}?{params}" if params else base

    return product_url


def _price_to_int(s: str | None) -> int | None:
    if not s:
        return None
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else None


def _discount_pct(current: str | None, original: str | None, explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    c, o = _price_to_int(current), _price_to_int(original)
    if c and o and o > 0 and c < o:
        return round((o - c) / o * 100)
    return None


# ── Amazon scraper (Playwright) ──────────────────────────────────────────────
async def scrape_amazon(max_per_category: int = 3, categories: list[dict] | None = None) -> list[dict[str, Any]]:
    from playwright.async_api import async_playwright

    cats = categories or DEAL_CATEGORIES
    deals: list[dict[str, Any]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(user_agent=_UA, viewport={"width": 1366, "height": 900},
                                        locale="en-IN")
        page = await ctx.new_page()
        for cat in cats:
            url = (f"https://www.amazon.in/s?k={cat['amazon_kw'].replace(' ', '+')}"
                   f"&rh=p_n_pct-off-with-tax:{_AMAZON_NODE_60}&s=discount-rank&i={cat['amazon_i']}")
            try:
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cards = await page.query_selector_all('[data-component-type="s-search-result"]')
            except Exception:
                continue
            taken = 0
            for card in cards:
                if taken >= max_per_category:
                    break
                try:
                    asin = await card.get_attribute("data-asin")
                    if not asin:
                        continue
                    t_el = await card.query_selector("h2 span")
                    title = (await t_el.inner_text()).strip() if t_el else None
                    cur_el = await card.query_selector(".a-price-whole")
                    cur = (await cur_el.inner_text()).strip() if cur_el else None
                    orig_el = await card.query_selector(".a-text-price .a-offscreen")
                    orig = (await orig_el.inner_text()).strip() if orig_el else None
                    img_el = await card.query_selector(".s-image")
                    img = await img_el.get_attribute("src") if img_el else None
                    pct = _discount_pct(cur, orig, None)
                    if not (title and pct):
                        continue
                    product_url = f"https://www.amazon.in/dp/{asin}"
                    deals.append({
                        "platform": "Amazon", "category": cat["category"], "title": title,
                        "current_price": f"₹{_price_to_int(cur)}" if cur else None,
                        "original_price": f"₹{_price_to_int(orig)}" if orig else None,
                        "discount_pct": pct, "image_url": img, "product_url": product_url,
                        "affiliate_url": build_affiliate_link(product_url, "Amazon"),
                    })
                    taken += 1
                except Exception:
                    continue
        await browser.close()
    return deals


# ── Flipkart scraper (Playwright, class-name-agnostic) ───────────────────────
async def scrape_flipkart(max_per_category: int = 3, categories: list[dict] | None = None) -> list[dict[str, Any]]:
    from playwright.async_api import async_playwright

    cats = categories or DEAL_CATEGORIES
    deals: list[dict[str, Any]] = []
    # Walk the DOM from each ₹price leaf up to its product card (link with /p/).
    extract_js = r"""
    () => {
      const out = [];
      const priceEls = [...document.querySelectorAll('*')].filter(el =>
        el.children.length === 0 && /^₹[\d,]+$/.test((el.textContent||'').trim()));
      for (const priceEl of priceEls) {
        let c = priceEl;
        for (let i = 0; i < 8 && c; i++) {
          c = c.parentElement;
          if (!c) break;
          const link = c.querySelector('a[href*="/p/"]');
          if (link) {
            const texts = [...c.querySelectorAll('*')].filter(e=>e.children.length===0)
              .map(e=>(e.textContent||'').trim()).filter(Boolean);
            const img = c.querySelector('img');
            out.push({href: link.getAttribute('href'),
                      texts: texts,
                      img: img ? (img.getAttribute('src')||'') : ''});
            break;
          }
        }
      }
      return out;
    }
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(user_agent=_UA, viewport={"width": 1366, "height": 900}, locale="en-IN")
        page = await ctx.new_page()
        for cat in cats:
            kw = cat["flipkart_kw"].replace(" ", "+")
            url = f"https://www.flipkart.com/search?q={kw}&sort=discount_desc"
            try:
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                raw = await page.evaluate(extract_js)
            except Exception:
                continue
            taken = 0
            seen: set[str] = set()
            for r in raw or []:
                if taken >= max_per_category:
                    break
                href, texts = r.get("href"), r.get("texts") or []
                if not href or href in seen:
                    continue
                prices = [t for t in texts if re.match(r"^₹[\d,]+$", t)]
                disc = next((t for t in texts if re.search(r"\d+%\s*off", t, re.I)), None)
                title = next((t for t in texts if len(t) > 12 and not t.startswith("₹")
                              and "% off" not in t.lower()), None)
                pct = None
                if disc:
                    m = re.search(r"(\d+)%", disc)
                    pct = int(m.group(1)) if m else None
                cur = prices[0] if prices else None
                orig = prices[1] if len(prices) > 1 else None
                pct = _discount_pct(cur, orig, pct)
                if not (title and pct):
                    continue
                seen.add(href)
                product_url = "https://www.flipkart.com" + href.split("?")[0]
                deals.append({
                    "platform": "Flipkart", "category": cat["category"], "title": title[:140],
                    "current_price": cur, "original_price": orig, "discount_pct": pct,
                    "image_url": r.get("img") or None, "product_url": product_url,
                    "affiliate_url": build_affiliate_link(product_url, "Flipkart"),
                })
                taken += 1
        await browser.close()
    return deals


# ── Orchestrator with the 80%/65% discount policy ────────────────────────────
async def get_fresh_deals(
    platforms: list[str] | None = None,
    max_per_category: int = 3,
    categories: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Scrape today's deals, then apply the discount policy: prefer >=80%, else
    fall back down to >=65% (never below). Returns [] on total failure so the
    caller can fall back to grabon.in coupon pages."""
    platforms = platforms or [s.strip() for s in (settings.DEAL_PLATFORMS or "Amazon,Flipkart").split(",") if s.strip()]
    pref, floor = settings.DEAL_PREFERRED_DISCOUNT, settings.DEAL_MIN_DISCOUNT

    cache_key = f"{','.join(sorted(platforms))}|{max_per_category}|{pref}|{floor}"
    if (_DEAL_CACHE["deals"] is not None and _DEAL_CACHE["key"] == cache_key
            and (time.time() - _DEAL_CACHE["ts"]) < _DEAL_CACHE_TTL_SEC):
        return _DEAL_CACHE["deals"]

    raw: list[dict[str, Any]] = []
    tasks = []
    if "Amazon" in platforms:
        tasks.append(scrape_amazon(max_per_category, categories))
    if "Flipkart" in platforms:
        tasks.append(scrape_flipkart(max_per_category, categories))
    for res in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(res, list):
            raw.extend(res)

    # Apply the discount policy PER CATEGORY (prefer >=pref, else >=floor) and
    # round-robin across categories so the mix spans ALL categories (fashion,
    # electronics, home, beauty, …) instead of clustering on whichever category
    # happens to have the highest-discount outliers (e.g. grocery).
    by_cat: dict[str, list[dict]] = {}
    for d in raw:
        if (d.get("discount_pct") or 0) >= floor:
            by_cat.setdefault(d.get("category") or "Other", []).append(d)

    ranked: dict[str, list[dict]] = {}
    for cat, ds in by_cat.items():
        top = [d for d in ds if (d.get("discount_pct") or 0) >= pref]
        picks = top if top else ds
        picks.sort(key=lambda d: d.get("discount_pct") or 0, reverse=True)
        ranked[cat] = picks

    # Interleave categories (round-robin) for a diverse, balanced deal list.
    order = [c["category"] for c in (categories or DEAL_CATEGORIES) if c["category"] in ranked]
    order += [c for c in ranked if c not in order]
    chosen: list[dict] = []
    i = 0
    while any(i < len(ranked[c]) for c in order):
        for c in order:
            if i < len(ranked[c]):
                chosen.append(ranked[c][i])
        i += 1

    _DEAL_CACHE.update(key=cache_key, deals=chosen, ts=time.time())
    return chosen


# ── Adapt a deal to the content pipeline's item shape ────────────────────────
def deal_to_content_item(deal: dict[str, Any]) -> dict[str, Any]:
    price = deal.get("current_price") or ""
    orig = deal.get("original_price") or ""
    pct = deal.get("discount_pct")
    body = (f"{deal.get('platform')} {deal.get('category')} deal: {deal.get('title')}. "
            f"Now {price}" + (f" (was {orig})" if orig else "") + f" — {pct}% OFF.")
    return {
        "title": f"{pct}% OFF — {deal.get('title')}",
        "body_text": body,
        "external_url": deal.get("affiliate_url") or deal.get("product_url"),
        "image_url": deal.get("image_url"),
        "published_at": None,
        "format_tag": None,
        "_deal": deal,
    }
