"""Telegram public-web scraping (no login) — resilient competitor data source.

Telethon (MTProto user session) is the primary way we read Telegram, but it fails
when the session is dead/expired or a channel isn't surfaced by in-app search. This
module scrapes Telegram's PUBLIC web preview instead:

    https://t.me/s/<handle>

which renders a channel's recent posts + subscriber count as static HTML for ANY
public channel — no account, no session. We use it to (a) CONFIRM a brand's handle
(verify a candidate actually resolves to a channel) and (b) READ competitor data
(subscribers, recent post text + views) when Telethon can't.

httpx first (cheap); Playwright Chromium as a fallback if the datacenter IP is
blocked. Respects SCRAPER_PROXY like the deal scrapers.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from config import settings

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Handles that are never real competitor channels.
_BAD_HANDLES = {"s", "share", "joinchat", "addstickers", "proxy", "socks", "iv",
                "telegram", "durov", "username", "c"}


def _httpx_kwargs() -> dict:
    raw = getattr(settings, "SCRAPER_PROXY", None)
    return {"proxy": raw} if raw else {}


def _parse_count(s: str | None) -> int | None:
    """'12.3K' → 12300, '1.2M' → 1200000, '12 345' → 12345."""
    if not s:
        return None
    s = s.strip().replace(",", "").replace(" ", "").replace(" ", "")
    m = re.match(r"^([\d.]+)([KkMm]?)", s)
    if not m:
        return None
    num = float(m.group(1))
    mult = {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)
    return int(num * mult)


async def _fetch_html(url: str, timeout: float = 8.0) -> str | None:
    """GET url as HTML via httpx. None on failure.

    Deliberately httpx-only: t.me/s and the search pages are static HTML that
    httpx fetches fine (verified from the Railway datacenter). A per-call Playwright
    fallback was removed — with dozens of fetches per competitor run it launched a
    browser per hiccup and made runs take 10+ minutes."""
    import httpx
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout,
                                     headers={"User-Agent": _UA}, **_httpx_kwargs()) as c:
            r = await c.get(url)
            if r.status_code < 400 and r.text:
                return r.text
    except Exception:
        pass
    return None


def _parse_preview(html: str, handle: str) -> dict[str, Any] | None:
    """Parse a t.me/s/<handle> page into channel data, or None if it's not a real
    public channel preview."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # A valid channel preview has the channel header + message widgets. A missing /
    # private / username-taken page has neither.
    if not soup.select_one(".tgme_channel_info, .tgme_page, .tgme_widget_message"):
        return None

    title_el = soup.select_one(".tgme_channel_info_header_title, .tgme_page_title")
    title = title_el.get_text(strip=True) if title_el else None

    member_count = None
    for c in soup.select(".tgme_channel_info_counter"):
        typ = (c.select_one(".counter_type") or c).get_text(" ", strip=True).lower()
        if "subscriber" in typ:
            val = c.select_one(".counter_value")
            member_count = _parse_count(val.get_text(strip=True) if val else None)
            break
    # Fallback for the plain t.me/<handle> page (when /s/ 302-redirects to it):
    # subscriber count lives in .tgme_page_extra ("12 345 subscribers").
    if member_count is None:
        extra = soup.select_one(".tgme_page_extra")
        if extra:
            m = re.search(r"([\d.,\sKMkm]+?)\s*(?:subscriber|member)", extra.get_text(" ", strip=True))
            if m:
                member_count = _parse_count(m.group(1))

    posts: list[dict[str, Any]] = []
    for w in soup.select(".tgme_widget_message"):
        txt_el = w.select_one(".tgme_widget_message_text")
        text = txt_el.get_text("\n", strip=True) if txt_el else ""
        views_el = w.select_one(".tgme_widget_message_views")
        views = _parse_count(views_el.get_text(strip=True)) if views_el else None
        time_el = w.select_one("time[datetime]")
        posted_at = time_el.get("datetime") if time_el else None
        if text or views:
            posts.append({"text": text, "views": views, "posted_at": posted_at})

    # Require at least one real signal (subscribers or posts) to call it valid.
    if member_count is None and not posts:
        return None
    return {
        "username": handle.lstrip("@").lower(),
        "title": title,
        "member_count": member_count,
        "posts": posts,
        "source": "tme_web",
    }


async def fetch_tme_preview(handle: str) -> dict[str, Any] | None:
    """Scrape https://t.me/s/<handle> → {username, title, member_count, posts[]} or
    None if the handle isn't a public channel."""
    h = handle.lstrip("@").strip()
    if not h or h.lower() in _BAD_HANDLES:
        return None
    html = await _fetch_html(f"https://t.me/s/{h}")
    return _parse_preview(html, h) if html else None


async def verify_handle(handle: str) -> bool:
    return (await fetch_tme_preview(handle)) is not None


def _slug_candidates(brand: str) -> list[str]:
    base = re.sub(r"[^a-z0-9]", "", brand.lower())
    if len(base) < 3:
        return []
    return list(dict.fromkeys([
        base, f"{base}official", f"{base}_official", f"{base}deals",
        f"{base}offers", f"{base}india", f"official{base}",
    ]))


async def _search_handles(brand: str) -> list[str]:
    """Find candidate t.me handles for a brand via web search (Bing + DuckDuckGo
    HTML endpoints — scraped directly, not via the DDGS API that gets rate-limited)."""
    from tools.competitor import extract_telegram_usernames
    key = re.sub(r"[^a-z0-9]", "", brand.lower())[:6]
    queries = [
        f"https://www.bing.com/search?q={brand}+telegram+channel",
        f"https://html.duckduckgo.com/html/?q={brand}+telegram+channel",
    ]
    out: list[str] = []
    for url in queries:
        html = await _fetch_html(url, timeout=12.0)
        if not html:
            continue
        for u in extract_telegram_usernames(html):
            ul = u.lower()
            if ul in _BAD_HANDLES or ul in out:
                continue
            # Prefer handles that share the brand key; keep others as weak fallback.
            out.append(ul)
    # brand-key matches first
    out.sort(key=lambda u: 0 if key and key in u else 1)
    return out[:8]


def _is_relevant(brand: str, data: dict[str, Any]) -> bool:
    """Guard against false positives (e.g. a generic '@media' handle from search
    noise): the resolved channel must reference the brand in its handle or title."""
    key = re.sub(r"[^a-z0-9]", "", brand.lower())[:5]
    if not key:
        return False
    hay = f"{data.get('username','')} {(data.get('title') or '')}".lower()
    hay = re.sub(r"[^a-z0-9]", "", hay)
    return key in hay


async def resolve_brand_handle(brand: str) -> dict[str, Any] | None:
    """Resolve a brand → its verified Telegram channel by scraping the public web.

    Tries web-search handles first, then brand-slug guesses, verifying each against
    t.me/s and requiring the result to actually reference the brand. Returns the
    first relevant match with its preview data, else None (never a wrong channel)."""
    tried: set[str] = set()
    # Cap total verifications per brand — each is one httpx GET; keep runs fast.
    candidates = (await _search_handles(brand) + _slug_candidates(brand))[:6]
    matches: list[dict[str, Any]] = []
    for h in candidates:
        h = h.lstrip("@").lower()
        if h in tried or h in _BAD_HANDLES:
            continue
        tried.add(h)
        data = await fetch_tme_preview(h)
        if data and _is_relevant(brand, data):
            matches.append(data)
    if not matches:
        return None
    # Prefer the largest real channel (avoids tiny/dead look-alikes like a 10-member
    # '@brandofficial' when the brand's main channel has tens of thousands).
    matches.sort(key=lambda d: d.get("member_count") or 0, reverse=True)
    return matches[0]
