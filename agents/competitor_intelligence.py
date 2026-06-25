"""Competitor Intelligence Agent (Phase 3 — brand-centric).

Runs AFTER Channel DNA (needs the detected category/brand). Discovers the
channel's REAL competitor brands via web search, finds each brand's Telegram
channel, benchmarks them, and feeds benchmarks + topic gaps to the Strategy agent.

Flow:
  1. web-search the brand's real competitor brands (LLM extracts names)
  2. for each brand -> find its Telegram channel (web search, TG fallback)
  3. resolve + enrich (members, top posts, metrics)
  4. rank + compute benchmarks (avg subs/ER/freq, my gap, top competitor)
  5. persist top 10

    python -m agents.competitor_intelligence --channel @techdigest_in
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from agents.base import BaseAgent
from tools.channel_dna import get_channel_category
from tools.channels import get_channel_context, get_or_create_channel, update_channel_meta
from tools.competitor import (
    CATEGORY_SEARCH_KEYWORDS,
    _brand_key,
    _is_spam_channel,
    channel_keyword_set,
    compute_benchmarks,
    compute_competitor_metrics,
    discover_channels_by_keywords,
    discover_competitor_brands,
    find_brand_telegram_channels,
    get_competitor_top_posts,
    get_telegram_recommended_channels,
    get_tracked_usernames,
    prune_stale_competitors,
    prune_unqualified_competitors,
    qualifies_as_competitor,
    rank_competitors,
    save_competitors,
)
from tools.shared import get_channel_posts, get_telegram_channel_info
from tools.telegram_client import telethon_session

MAX_CANDIDATES = 30
TOP_N = 12
MIN_BEFORE_FALLBACK = 8
BRAND_RESOLVE_LIMIT = 12  # resolve top-N brands (1 web search each) — rate-limit budget


class CompetitorIntelligenceAgent(BaseAgent):
    name = "competitor_intelligence"

    async def _execute(self, channel_id: str, *, client=None, **_: Any) -> dict[str, Any]:
        ctx = await get_channel_context(channel_id)
        if not ctx:
            raise ValueError(f"Channel {channel_id} not found")
        if client is not None:
            return await self._run(channel_id, ctx, client)
        async with telethon_session() as c:
            return await self._run(channel_id, ctx, c)

    async def _run(self, channel_id, ctx, client) -> dict[str, Any]:
        managed = ctx["username"]
        category = ctx.get("category")
        topics = ctx.get("primary_topics") or []

        # depends on DNA category — if missing, detect from the channel's own posts
        if not category:
            try:
                posts = (await get_channel_posts(client, managed, days=30))["posts"]
                category, sub = get_channel_category(posts, managed)
                if category:
                    await update_channel_meta(channel_id, category=category, sub_category=sub)
            except Exception:
                category = None

        brand = ctx.get("display_name") or managed
        sources_used: list[str] = []
        tracked = await get_tracked_usernames(channel_id)
        my_subs = ctx.get("subscriber_count") or 0
        managed_lower = managed.lstrip("@").lower()

        # Shared dedup set — grows as each source adds channels.
        seen_handles: set[str] = set(tracked) | {managed_lower}

        async def _enrich_channel(h: str, source: str) -> dict | None:
            """Fetch info+posts for a handle, qualify it, return entry or None."""
            hl = h.lstrip("@").lower()
            if hl in seen_handles or _is_spam_channel(hl):
                return None
            try:
                info = await get_telegram_channel_info(client, h)
            except Exception:
                return None
            members = info.get("member_count") or 0
            posts = (await get_competitor_top_posts(client, h))["posts"]
            metrics = compute_competitor_metrics(posts, members)
            ok, _ = qualifies_as_competitor(members, len(posts), metrics, my_subs)
            if not ok:
                return None
            seen_handles.add(hl)
            return {
                "display_name": info.get("title") or h,
                "username": h.lstrip("@"), "source": source,
                "competitor_tg_id": info.get("channel_id"),
                "subscriber_count": members, "avg_er": metrics["avg_er"],
                "post_frequency_per_day": metrics["post_frequency_per_day"],
                "top_themes": metrics["top_themes"],
                "has_disappearing_messages": bool(info.get("has_disappearing_messages")),
                "posts": posts, "on_telegram": True,
            }

        # 1. Category-keyword Telegram search — PRIMARY for aggregator categories
        #    (deals, coupons, shopping). Finds real peers by what they post about
        #    rather than by brand name, so it surfaces CashKaro, CouponDunia,
        #    DesiDime etc. directly without relying on web-search brand guessing.
        kw_entries: list[dict] = []
        cat_keywords = CATEGORY_SEARCH_KEYWORDS.get((category or "").lower().strip(), [])
        if cat_keywords:
            kw_channels = await discover_channels_by_keywords(client, cat_keywords)
            if kw_channels:
                sources_used.append("category_keyword_search")
            for ch in kw_channels:
                h = ch.get("username")
                if not h:
                    continue
                entry = await _enrich_channel(f"@{h}", "category_keyword_search")
                if entry:
                    kw_entries.append(entry)

        # 2. Telegram's own "similar channels" (GetChannelRecommendations).
        tg_rec_entries: list[dict] = []
        tg_recs = await get_telegram_recommended_channels(client, managed)
        if tg_recs["channels"]:
            sources_used.append("telegram_recommendations")
        for rec in tg_recs["channels"]:
            h = rec.get("username")
            if not h:
                continue
            entry = await _enrich_channel(f"@{h}", "telegram_recommendations")
            if entry:
                entry["display_name"] = rec.get("display_name") or entry["display_name"]
                tg_rec_entries.append(entry)

        # 3. Market competitor brands via web research + LLM.
        #    These are REAL market rivals (business names) — may or may not have
        #    a Telegram channel. Listed regardless; TG data added when found.
        brands = await discover_competitor_brands(brand, category, topics) or []
        if brands:
            sources_used.append("market_research")

        # 4. For each brand, find its Telegram channel (Telegram search first).
        brand_entries: list[dict] = []
        rejected: list[dict] = []
        for b in brands[:BRAND_RESOLVE_LIMIT]:
            market_entry = {
                "display_name": b, "username": _brand_key(b), "source": "market_research",
                "subscriber_count": None, "avg_er": None, "post_frequency_per_day": None,
                "top_themes": [], "has_disappearing_messages": False, "posts": [], "on_telegram": False,
            }
            for h in await find_brand_telegram_channels(b, client):
                entry = await _enrich_channel(h, "market_research")
                if entry:
                    market_entry.update(entry)
                    break
                else:
                    hl = h.lstrip("@").lower()
                    if hl not in seen_handles and not _is_spam_channel(hl):
                        rejected.append({"brand": b, "handle": h, "reason": "did not qualify"})
            brand_entries.append(market_entry)

        # 5. Merge: keyword search first (most category-accurate), then TG recs,
        #    then brand-matched. Market-only entries trail at the end.
        all_entries = kw_entries + tg_rec_entries + brand_entries

        # 6. Rank: on-Telegram channels by composite score, market-only in order.
        keywords = channel_keyword_set(category, ctx.get("sub_category"), topics)
        with_metrics = rank_competitors([e for e in all_entries if e["on_telegram"]], keywords)
        market_only = [e for e in all_entries if not e["on_telegram"]]
        for i, e in enumerate(market_only, start=len(with_metrics) + 1):
            e["rank"] = i
            e["rank_score"] = None
        ordered = (with_metrics + market_only)[:TOP_N]

        benchmarks = compute_benchmarks(with_metrics, {"avg_er": ctx.get("avg_er")})
        run_started = datetime.now(timezone.utc)
        saved = await save_competitors(channel_id, ordered)
        pruned = await prune_unqualified_competitors(channel_id)
        # Replace-semantics: if this run produced a healthy set, drop competitors
        # left over from an earlier (e.g. mis-categorised) run so the list reflects
        # the channel's CURRENT niche instead of accumulating stale entries.
        if len(ordered) >= 3:
            stale = await prune_stale_competitors(channel_id, run_started)
            pruned = {"removed": pruned["removed"] + stale["removed"], "kept": stale["kept"]}

        return {
            "brand": brand,
            "market_competitors": brands,
            "total_found": len(ordered),
            "on_telegram": len(with_metrics),
            "market_only": len(market_only),
            "rejected_channels": rejected[:5],
            "pruned_junk": pruned["removed"],
            "competitors_now": pruned["kept"],
            "saved": saved["upserted"],
            "sources_used": sorted(set(sources_used)),
            "benchmarks": benchmarks,
            "top_10": [
                {"name": c["display_name"], "username": c["username"] if c["on_telegram"] else None,
                 "rank": c["rank"], "subscriber_count": c.get("subscriber_count"), "avg_er": c.get("avg_er")}
                for c in ordered
            ],
        }

    def _summarize(self, result: dict[str, Any]) -> dict[str, Any]:
        b = result.get("benchmarks") or {}
        return {
            "total_found": result.get("total_found"),
            "saved": result.get("saved"),
            "competitor_avg_er": b.get("competitor_avg_er"),
            "er_gap": b.get("er_gap"),
        }


async def _main(username: str) -> None:
    channel = await get_or_create_channel(username)
    agent = CompetitorIntelligenceAgent(trigger="manual")
    result = await agent.run(channel["id"])
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Competitor Intelligence Agent")
    parser.add_argument("--channel", required=True, help="Telegram @username")
    args = parser.parse_args()
    asyncio.run(_main(args.channel))
