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
from typing import Any

from config import settings

# ── Categories (comprehensive) ───────────────────────────────────────────────
# Amazon needs (search keyword, search index `i`); Flipkart needs a keyword.
DEAL_CATEGORIES: list[dict[str, str]] = [
    {"category": "Electronics",    "amazon_kw": "electronics",        "amazon_i": "electronics", "flipkart_kw": "electronics"},
    {"category": "Mobiles",        "amazon_kw": "smartphones",        "amazon_i": "electronics", "flipkart_kw": "mobiles"},
    {"category": "Fashion Men",    "amazon_kw": "mens clothing",      "amazon_i": "apparel",     "flipkart_kw": "mens fashion"},
    {"category": "Fashion Women",  "amazon_kw": "womens clothing",    "amazon_i": "apparel",     "flipkart_kw": "womens fashion"},
    {"category": "Footwear",       "amazon_kw": "shoes",              "amazon_i": "shoes",       "flipkart_kw": "footwear"},
    {"category": "Home & Kitchen", "amazon_kw": "home kitchen",       "amazon_i": "kitchen",     "flipkart_kw": "home kitchen"},
    {"category": "Home Decor",     "amazon_kw": "home decor",         "amazon_i": "kitchen",     "flipkart_kw": "home decor"},
    {"category": "Appliances",     "amazon_kw": "home appliances",    "amazon_i": "appliances",  "flipkart_kw": "appliances"},
    {"category": "Beauty",         "amazon_kw": "beauty products",    "amazon_i": "beauty",      "flipkart_kw": "beauty"},
    {"category": "Sports",         "amazon_kw": "sports fitness",     "amazon_i": "sporting",    "flipkart_kw": "sports fitness"},
    {"category": "Watches",        "amazon_kw": "watches",            "amazon_i": "watches",     "flipkart_kw": "watches"},
    {"category": "Bags & Luggage", "amazon_kw": "backpacks luggage",  "amazon_i": "luggage",     "flipkart_kw": "bags"},
    {"category": "Toys",           "amazon_kw": "toys games",         "amazon_i": "toys",        "flipkart_kw": "toys"},
    {"category": "Grocery",        "amazon_kw": "grocery",            "amazon_i": "grocery",     "flipkart_kw": "grocery"},
]

# Amazon India discount filter nodes (rh=p_n_pct-off-with-tax:<node>).
# We scrape the 60%+ node (broad) and apply the 80%/65% policy in Python.
_AMAZON_NODE_60 = "2665394031"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ── Affiliate links ───────────────────────────────────────────────────────────
def build_affiliate_link(product_url: str, platform: str) -> str:
    """Append the configured affiliate tag. Amazon -> ?tag=<AMAZON_AFFILIATE_TAG>;
    Flipkart -> append tag only if FLIPKART_AFFILIATE_TAG is set, else raw URL."""
    if not product_url:
        return product_url
    base = product_url.split("?")[0].rstrip("/")
    if platform == "Amazon" or "amazon.in" in product_url:
        tag = settings.AMAZON_AFFILIATE_TAG
        return f"{base}/?tag={tag}" if tag else base
    if platform == "Flipkart" or "flipkart.com" in product_url:
        tag = settings.FLIPKART_AFFILIATE_TAG
        return f"{base}?affid={tag}" if tag else product_url
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

    raw: list[dict[str, Any]] = []
    tasks = []
    if "Amazon" in platforms:
        tasks.append(scrape_amazon(max_per_category, categories))
    if "Flipkart" in platforms:
        tasks.append(scrape_flipkart(max_per_category, categories))
    for res in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(res, list):
            raw.extend(res)

    valid = [d for d in raw if (d.get("discount_pct") or 0) >= floor]
    top = [d for d in valid if (d.get("discount_pct") or 0) >= pref]
    chosen = top if top else valid
    chosen.sort(key=lambda d: d.get("discount_pct") or 0, reverse=True)
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
