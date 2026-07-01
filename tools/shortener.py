"""GrabOn URL shortener — turns affiliate deal links into grbn.in short links.

Called AFTER affiliate-link generation for the GrabOn (deals) channel: the short
link is what appears in the post. Fail-open — if the shortener is unreachable the
original affiliate URL is used, so a post is never broken.

    POST {SHORTENER_API_URL}  {"originalUrl": "..."}  ->  {"data": {"shortUrl": "..."}}
"""
from __future__ import annotations

import asyncio
import time
from typing import Iterable

from config import settings

# Short-lived cache so the same product link isn't shortened twice in a run.
_CACHE: dict[str, str] = {}
_CACHE_TS: dict[str, float] = {}
_TTL = 1800.0


async def shorten_url(url: str) -> str:
    """Return the grbn.in short link for `url`, or `url` unchanged on any failure."""
    if not url or not str(url).startswith(("http://", "https://")):
        return url
    api = getattr(settings, "SHORTENER_API_URL", None)
    if not api:
        return url
    now = time.time()
    cached = _CACHE.get(url)
    if cached and (now - _CACHE_TS.get(url, 0)) < _TTL:
        return cached
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(api, json={"originalUrl": url},
                             headers={"Content-Type": "application/json"})
            if r.status_code < 400:
                short = ((r.json() or {}).get("data") or {}).get("shortUrl")
                if short:
                    _CACHE[url] = short
                    _CACHE_TS[url] = now
                    return short
    except Exception:
        pass
    return url


async def shorten_many(urls: Iterable[str]) -> dict[str, str]:
    """Shorten a set of URLs concurrently → {original: short}. Failures map to self."""
    uniq = [u for u in dict.fromkeys(urls) if u]
    shorts = await asyncio.gather(*[shorten_url(u) for u in uniq], return_exceptions=True)
    out: dict[str, str] = {}
    for u, s in zip(uniq, shorts):
        out[u] = s if isinstance(s, str) else u
    return out
