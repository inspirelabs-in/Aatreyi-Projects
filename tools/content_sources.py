"""Content source management — default feeds per category + CRUD."""
from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import ContentSource, SourceType

# Categories whose content expires quickly (deals, coupons, etc.).
# For these, the seeder tries to auto-detect the channel's own website from its posts.
_EPHEMERAL_CATEGORIES = {"deals", "shopping", "coupons", "offers"}

# URL shorteners commonly used by deal channels — we skip these when counting
# domains and instead follow one redirect to find the real domain.
_URL_SHORTENERS = {"grbn.in", "bit.ly", "t.co", "ow.ly", "goo.gl", "tinyurl.com", "rb.gy"}

# Social/messaging domains to ignore during domain detection.
_SKIP_DOMAINS = {
    "t.me", "telegram.me", "twitter.com", "instagram.com",
    "facebook.com", "youtube.com", "youtu.be",
} | _URL_SHORTENERS

_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+", re.IGNORECASE)


def _extract_domains(posts: list[dict]) -> Counter:
    """Count external domains linked in channel posts."""
    domains: list[str] = []
    for post in posts:
        text = (post.get("text") or "") + " " + (post.get("external_url") or "")
        for url in _URL_RE.findall(text):
            try:
                host = urlparse(url).netloc.lower().lstrip("www.")
                if host and host not in _SKIP_DOMAINS:
                    domains.append(host)
            except Exception:
                pass
    return Counter(domains)


async def _resolve_shortener_domain(posts: list[dict]) -> str | None:
    """Follow one URL shortener link from channel posts to find the real domain."""
    import httpx
    for post in posts:
        text = (post.get("text") or "") + " " + (post.get("external_url") or "")
        for url in _URL_RE.findall(text):
            try:
                host = urlparse(url).netloc.lower().lstrip("www.")
                if host in _URL_SHORTENERS:
                    async with httpx.AsyncClient(timeout=6, follow_redirects=True,
                                                  headers={"User-Agent": "Mozilla/5.0"}) as c:
                        r = await c.head(url)
                        real = urlparse(str(r.url)).netloc.lower().lstrip("www.")
                        if real and real not in _SKIP_DOMAINS:
                            return real
            except Exception:
                pass
    return None


async def _detect_channel_website(posts: list[dict]) -> str | None:
    """Return the channel's primary website URL inferred from its posts, or None.

    Counts all external domains the channel links to, skipping social/messaging
    and URL shorteners. For shortener-heavy channels (deal sites), follows one
    redirect to discover the real domain (e.g. grbn.in → grabon.in)."""
    counts = _extract_domains(posts)
    if counts:
        top_domain, top_count = counts.most_common(1)[0]
        if top_count >= 2:
            return f"https://www.{top_domain}/"
    # Only shorteners found — follow one to discover the real site.
    real = await _resolve_shortener_domain(posts)
    if real:
        return f"https://www.{real}/"
    return None

# Content sources by channel category — (name, url, type).
# type is "rss" or "website"; "website" is scraped via scrape_website().
DEFAULT_FEEDS_BY_CATEGORY: dict[str, list[tuple[str, str, str]]] = {
    "deals": [
        ("GrabOn", "https://www.grabon.in/", "website"),
        ("GrabOn Offers", "https://www.grabon.in/offers/", "website"),
    ],
    "tech": [
        ("TechCrunch", "https://techcrunch.com/feed/", "rss"),
        ("Hacker News", "https://hnrss.org/frontpage", "rss"),
    ],
    "crypto": [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "rss"),
    ],
    "finance": [
        ("Investopedia", "https://www.investopedia.com/feedbuilder/feed/getfeed?feedName=rss_headline", "rss"),
    ],
    "news": [
        ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml", "rss"),
    ],
    "sports": [
        ("ESPN Top", "https://www.espn.com/espn/rss/news", "rss"),
    ],
    "education": [
        ("EdSurge", "https://www.edsurge.com/news.rss", "rss"),
    ],
    "health": [
        ("Medical News Today", "https://www.medicalnewstoday.com/rss", "rss"),
    ],
    "gaming": [
        ("IGN All", "https://feeds.feedburner.com/ign/all", "rss"),
    ],
    "business": [
        ("Harvard Business Review", "https://hbr.org/feed", "rss"),
    ],
    "shopping": [
        ("Retail Dive", "https://www.retaildive.com/feeds/news/", "rss"),
    ],
    "entertainment": [
        ("Variety", "https://variety.com/feed/", "rss"),
        ("Rolling Stone", "https://www.rollingstone.com/feed/", "rss"),
    ],
}
DEFAULT_FEEDS: list[tuple[str, str, str]] = [
    ("Hacker News", "https://hnrss.org/frontpage", "rss"),
]


def _feeds_for_category(category: str | None) -> list[tuple[str, str, str]]:
    if category:
        key = category.strip().lower()
        if key in DEFAULT_FEEDS_BY_CATEGORY:
            return DEFAULT_FEEDS_BY_CATEGORY[key]
    return DEFAULT_FEEDS


async def seed_default_sources(
    channel_id: str | uuid.UUID,
    category: str | None = None,
    posts: list[dict] | None = None,
) -> dict[str, Any]:
    """Add content sources when a channel has none yet.

    For ephemeral categories (deals, shopping, coupons): if channel posts are
    provided, auto-detects the channel's primary website by following the URLs
    it posts (incl. shorteners like grbn.in → grabon.in) and seeds that as the
    source — so each channel uses its own website rather than a generic default.
    Falls back to DEFAULT_FEEDS_BY_CATEGORY if detection fails."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(ContentSource.id).where(ContentSource.channel_id == cid).limit(1))
        ).scalar_one_or_none()
        if existing:
            return {"seeded": 0, "reason": "already_has_sources"}

    # For ephemeral categories, try to detect the channel's own website from posts.
    detected_url: str | None = None
    cat_key = (category or "").strip().lower()
    if cat_key in _EPHEMERAL_CATEGORIES and posts:
        detected_url = await _detect_channel_website(posts)

    async with AsyncSessionLocal() as session:
        added = 0
        if detected_url:
            session.add(ContentSource(
                channel_id=cid,
                type=SourceType.website,
                url=detected_url,
                name="Channel Website",
                category=category,
                is_active=True,
            ))
            added += 1
        else:
            for name, url, src_type in _feeds_for_category(category):
                session.add(ContentSource(
                    channel_id=cid,
                    type=SourceType(src_type),
                    url=url,
                    name=name,
                    category=category,
                    is_active=True,
                ))
                added += 1
        await session.commit()
    return {"seeded": added, "category": category, "detected_url": detected_url}


async def list_sources(channel_id: str | uuid.UUID) -> list[dict[str, Any]]:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(ContentSource)
                .where(ContentSource.channel_id == cid)
                .order_by(ContentSource.is_active.desc(), ContentSource.name.asc())
            )
        ).scalars().all()
    return [
        {
            "id": str(r.id),
            "type": r.type.value,
            "url": r.url,
            "name": r.name,
            "category": r.category,
            "is_active": r.is_active,
            "avg_quality_score": r.avg_quality_score,
            "total_items_scored": r.total_items_scored,
        }
        for r in rows
    ]


async def add_source(
    channel_id: str | uuid.UUID,
    *,
    type: str,
    url: str,
    name: str | None = None,
) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    src_type = SourceType(type)
    async with AsyncSessionLocal() as session:
        row = ContentSource(
            channel_id=cid,
            type=src_type,
            url=url.strip(),
            name=(name or url).strip()[:128],
            is_active=True,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return {"id": str(row.id), "type": row.type.value, "url": row.url, "name": row.name}


async def update_source(
    source_id: str | uuid.UUID,
    *,
    is_active: bool | None = None,
    name: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    sid = uuid.UUID(str(source_id))
    async with AsyncSessionLocal() as session:
        row = (await session.execute(select(ContentSource).where(ContentSource.id == sid))).scalar_one_or_none()
        if not row:
            return {"updated": False}
        if is_active is not None:
            row.is_active = is_active
        if name is not None:
            row.name = name.strip()[:128]
        if url is not None:
            row.url = url.strip()
        await session.commit()
    return {"updated": True, "id": str(sid)}


async def delete_source(source_id: str | uuid.UUID) -> dict[str, Any]:
    sid = uuid.UUID(str(source_id))
    async with AsyncSessionLocal() as session:
        row = (await session.execute(select(ContentSource).where(ContentSource.id == sid))).scalar_one_or_none()
        if not row:
            return {"deleted": False}
        await session.delete(row)
        await session.commit()
    return {"deleted": True, "id": str(sid)}
