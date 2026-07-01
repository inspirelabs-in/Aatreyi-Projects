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
    TOPIC_SIM_THRESHOLD,
    _brand_key,
    _is_spam_channel,
    channel_keyword_set,
    compute_benchmarks,
    compute_competitor_metrics,
    compute_content_similarity,
    compute_topic_similarity,
    discover_channels_by_keywords,
    discover_competitor_brands,
    extract_channel_topics,
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
from tools.competitor_intel import (
    analyze_posts,
    build_channel_intelligence,
    classify,
    llm_analyze_competitor,
    load_my_profile,
    similarity_breakdown,
)
from tools.shared import get_channel_posts, get_telegram_channel_info
from tools.telegram_client import telethon_session

MAX_CANDIDATES = 30
TOP_N = 12
MIN_BEFORE_FALLBACK = 8
BRAND_RESOLVE_LIMIT = 10  # resolve top-N brands — rate-limit budget

# Telegram allows ~30 API requests/30s per account. Cap concurrent calls to
# avoid FloodWaitError when enriching many channels in parallel.
_TG_SEM = asyncio.Semaphore(3)


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
        # If DB value is stale/null, read live from Telegram so the peer-ratio
        # gate (>= 5% of our size) has a real floor to enforce.
        if not my_subs:
            try:
                live = await get_telegram_channel_info(client, managed)
                my_subs = live.get("member_count") or 0
            except Exception:
                pass
        managed_lower = managed.lstrip("@").lower()

        # Shared dedup set — grows as each source adds channels.
        seen_handles: set[str] = set(tracked) | {managed_lower}

        async def _enrich_channel(h: str, source: str, skip_peer_ratio: bool = False) -> dict | None:
            """Fetch info+posts for a handle, qualify it, return entry or None.

            skip_peer_ratio=True for LLM-identified brands: they are explicitly
            known market rivals so we don't gate them on Telegram subscriber count
            relative to us (a brand may be huge on web/app but small on Telegram).
            """
            hl = h.lstrip("@").lower()
            if hl in seen_handles or _is_spam_channel(hl):
                return None
            # Primary: Telethon (MTProto). Fallback: Telegram's public web preview
            # (t.me/s) when the session can't reach the channel — so a confirmed
            # handle still yields data (subscribers, recent posts, themes).
            info: dict | None = None
            try:
                info = await get_telegram_channel_info(client, h)
            except Exception:
                info = None
            members = (info or {}).get("member_count") or 0
            posts = []
            if info is not None:
                try:
                    posts = (await get_competitor_top_posts(client, h))["posts"]
                except Exception:
                    posts = []
            web_sourced = False
            if info is None or (members == 0 and not posts):
                from tools.telegram_web import fetch_tme_preview
                web = await fetch_tme_preview(h)
                if web is None:
                    return None
                web_sourced = True
                members = web.get("member_count") or members
                # Map web posts to the metric shape (reactions/forwards unavailable
                # on the public preview → engagement rate is not measurable here).
                # posted_at is an ISO string on the web preview; metrics needs
                # datetime objects, so parse it (drop unparseable ones).
                from datetime import datetime as _dt
                def _iso(s):
                    try:
                        return _dt.fromisoformat(str(s).replace("Z", "+00:00")) if s else None
                    except Exception:
                        return None
                posts = [{"text": p.get("text") or "", "views": p.get("views") or 0,
                          "forwards": 0, "reactions": 0, "posted_at": _iso(p.get("posted_at"))}
                         for p in (web.get("posts") or [])]
                info = info or {"title": web.get("title"), "channel_id": None,
                                "has_disappearing_messages": False}
            metrics = compute_competitor_metrics(posts, members)
            peer_subs = 0 if skip_peer_ratio else my_subs
            ok, _ = qualifies_as_competitor(members, len(posts), metrics, peer_subs)
            if not ok:
                return None
            seen_handles.add(hl)
            return {
                "display_name": info.get("title") or h,
                "username": h.lstrip("@"), "source": source + ("+web" if web_sourced else ""),
                "competitor_tg_id": info.get("channel_id"),
                "subscriber_count": members,
                # Web preview has no reactions/forwards, so ER is unknown (not 0).
                "avg_er": None if web_sourced else metrics["avg_er"],
                "post_frequency_per_day": metrics["post_frequency_per_day"],
                "top_themes": metrics["top_themes"],
                "has_disappearing_messages": bool(info.get("has_disappearing_messages")),
                "posts": posts, "on_telegram": True,
            }

        # 1. Category-keyword search + Telegram recommendations + brand research
        #    run concurrently — all three are independent network/LLM calls.
        cat_keywords = CATEGORY_SEARCH_KEYWORDS.get((category or "").lower().strip(), [])
        kw_task = discover_channels_by_keywords(client, cat_keywords) if cat_keywords else asyncio.sleep(0, result=[])
        rec_task = get_telegram_recommended_channels(client, managed)
        brand_task = discover_competitor_brands(brand, category, topics)
        kw_channels, tg_recs, brands = await asyncio.gather(kw_task, rec_task, brand_task)
        brands = brands or []

        # Enrich all keyword-search and recommendation channels in parallel.
        async def _enrich_kw(ch: dict) -> dict | None:
            h = ch.get("username")
            if not h:
                return None
            async with _TG_SEM:
                return await _enrich_channel(f"@{h}", "category_keyword_search")

        async def _enrich_rec(rec: dict) -> dict | None:
            h = rec.get("username")
            if not h:
                return None
            async with _TG_SEM:
                entry = await _enrich_channel(f"@{h}", "telegram_recommendations")
            if entry:
                entry["display_name"] = rec.get("display_name") or entry["display_name"]
            return entry

        kw_results, rec_results = await asyncio.gather(
            asyncio.gather(*[_enrich_kw(ch) for ch in (kw_channels or [])]),
            asyncio.gather(*[_enrich_rec(rec) for rec in (tg_recs or {}).get("channels", [])]),
        )

        kw_entries: list[dict] = [e for e in kw_results if e]
        tg_rec_entries: list[dict] = [e for e in rec_results if e]
        if kw_entries:
            sources_used.append("category_keyword_search")
        if tg_rec_entries:
            sources_used.append("telegram_recommendations")

        # 2. Resolve each brand's Telegram channel in parallel.
        if brands:
            sources_used.append("market_research")

        rejected: list[dict] = []

        async def _resolve_brand(b: str) -> dict:
            market_entry = {
                "display_name": b, "username": _brand_key(b), "source": "market_research",
                "subscriber_count": None, "avg_er": None, "post_frequency_per_day": None,
                "top_themes": [], "has_disappearing_messages": False, "posts": [], "on_telegram": False,
            }
            async with _TG_SEM:
                handles = await find_brand_telegram_channels(b, client)
            for h in handles:
                async with _TG_SEM:
                    entry = await _enrich_channel(h, "market_research", skip_peer_ratio=True)
                if entry:
                    market_entry.update(entry)
                    break
                else:
                    hl = h.lstrip("@").lower()
                    if hl not in seen_handles and not _is_spam_channel(hl):
                        rejected.append({"brand": b, "handle": h, "reason": "did not qualify"})
            return market_entry

        brand_entries: list[dict] = list(await asyncio.gather(
            *[_resolve_brand(b) for b in brands[:BRAND_RESOLVE_LIMIT]]
        ))

        # 5. Merge all discovered candidates.
        all_entries = kw_entries + tg_rec_entries + brand_entries

        # 6. Topic + content similarity scoring and filtering.
        #    Extract the managed channel's own topics from DNA / context.
        #    For every on-Telegram candidate: compute Jaccard topic similarity,
        #    reject if below threshold (only when we have topics to compare),
        #    then ask the LLM to rate content-focus overlap.
        my_topics = [str(t).lower() for t in (topics or ctx.get("top_topics") or [])]
        for entry in all_entries:
            if not entry.get("on_telegram"):
                entry.setdefault("topic_similarity", 0.0)
                entry.setdefault("content_similarity", 0.0)
                continue
            cand_topics = extract_channel_topics(entry.get("posts") or [])
            entry["candidate_topics"] = cand_topics

            # Channels found via category keyword search are already category-vetted
            # by the search terms used to find them — skip the topic threshold check.
            # Jaccard on category-level topics (e.g. "deals") vs post-level topics
            # (e.g. "cashback", "amazon offers") always produces near-zero similarity
            # and would wrongly demote real peers like CashKaro / CouponDunia.
            if entry.get("source") == "category_keyword_search":
                entry["topic_similarity"] = 1.0
                cs = await compute_content_similarity(my_topics, cand_topics) if my_topics else 0.5
                entry["content_similarity"] = cs
                continue

            ts = compute_topic_similarity(my_topics, cand_topics) if my_topics else 0.5
            entry["topic_similarity"] = ts
            # Demote to market-only when topic overlap is too low.
            if my_topics and ts < TOPIC_SIM_THRESHOLD:
                rejected.append({
                    "brand": entry.get("display_name"),
                    "handle": entry.get("username"),
                    "reason": f"topic_sim={ts:.2f} < {TOPIC_SIM_THRESHOLD}",
                })
                entry["on_telegram"] = False
                entry["subscriber_count"] = None
                entry["content_similarity"] = 0.0
                continue
            cs = await compute_content_similarity(my_topics, cand_topics)
            entry["content_similarity"] = cs

        # 8. Rank: on-Telegram channels by composite score, market-only in order.
        keywords = channel_keyword_set(category, ctx.get("sub_category"), topics)
        with_metrics = rank_competitors([e for e in all_entries if e["on_telegram"]], keywords)
        market_only = [e for e in all_entries if not e["on_telegram"]]

        # 8b. COMPETITOR INTELLIGENCE (per spec): weighted similarity sub-scores,
        #     direct/aspirational/adjacent classification, and deep per-competitor
        #     analysis (media mix, best hours, CTA, strengths/weaknesses, why-won).
        #     Intelligence only — no recommendations. Re-rank by the spec-weighted
        #     similarity so the order reflects Audience/Topic/Lang/Format/Freq/Size.
        my_profile = await load_my_profile(channel_id)
        my_subs = my_profile.get("subscriber_count") or ctx.get("subscriber_count")
        INTEL_LLM_LIMIT = 8  # cap LLM calls per run
        for i, e in enumerate(with_metrics):
            analysis = analyze_posts(e.get("posts") or [])
            llm = (await llm_analyze_competitor(
                e.get("display_name") or e.get("username"), category, analysis.get("top_posts"))
                if i < INTEL_LLM_LIMIT else {})
            e["intelligence"] = {**analysis, **llm}
            bd = similarity_breakdown(my_profile, {
                "topic_similarity": e.get("topic_similarity"),
                "candidate_topics": e.get("candidate_topics"),
                "media_mix": analysis.get("media_mix"),
                "post_frequency_per_day": e.get("post_frequency_per_day"),
                "subscriber_count": e.get("subscriber_count"),
                "language": e.get("language"),
                "category": category,
            })
            e["similarity_breakdown"] = bd
            e["rank_score"] = bd["total"]  # spec-weighted similarity drives the rank
            e["competitor_type"] = classify(e.get("topic_similarity"), my_subs, e.get("subscriber_count"))
        with_metrics.sort(key=lambda c: c.get("rank_score") or 0, reverse=True)
        for i, e in enumerate(with_metrics, 1):
            e["rank"] = i
        for i, e in enumerate(market_only, start=len(with_metrics) + 1):
            e["rank"] = i
            e["rank_score"] = None
            e["competitor_type"] = "adjacent"
        ordered = (with_metrics + market_only)[:TOP_N]

        # 8c. Channel-level intelligence (facts only — gaps, trends, schedule, opps).
        channel_intel = build_channel_intelligence(with_metrics, my_profile)

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
            "competitor_intelligence": channel_intel,
            "classification": {
                "direct": [c["username"] for c in with_metrics if c.get("competitor_type") == "direct"][:5],
                "aspirational": [c["username"] for c in with_metrics if c.get("competitor_type") == "aspirational"][:3],
                "adjacent": [c["username"] for c in with_metrics if c.get("competitor_type") == "adjacent"][:3],
            },
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
