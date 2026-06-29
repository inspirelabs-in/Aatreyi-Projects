"""Content Intelligence Agent (Phase 6).

Per strategy_task (one post slot): fetch sources -> score (7 signals) ->
generate a Telegram-native post (or original fallback) -> push to review queue.

    python -m agents.content_intelligence --task <strategy_task_id>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from typing import Any

from agents.base import BaseAgent

log = logging.getLogger(__name__)
from tools.content import (
    add_to_review_queue,
    check_url_used,
    fetch_content_sources,
    fetch_rss_feed,
    generate_original_post,
    generate_post,
    get_strategy_task,
    load_content_context,
    maybe_auto_publish,
    save_content_item,
    save_content_score,
    scrape_deal_links,
    scrape_website,
    score_content_items,
    update_source_quality_score,
    _pick_recycle_item,
    _verify_url_active,
)
from tools.shared import get_channel_posts
from tools.telegram_client import telethon_session

GREEN_THRESHOLD = 4  # roadmap slot logic: take items with >=4 green signals


class ContentIntelligenceAgent(BaseAgent):
    name = "content_intelligence"

    def __init__(self, trigger: str = "post_slot"):
        super().__init__(trigger=trigger)

    async def _execute(self, channel_id: str, *, task_id: str, client=None, **_: Any) -> dict[str, Any]:
        task = await get_strategy_task(task_id)
        if not task:
            raise ValueError(f"strategy_task {task_id} not found")
        context = await load_content_context(channel_id)

        # Recycle slots reuse a past break-out post instead of fetching sources.
        # For deal/ephemeral content: first verify the candidate URL is still live.
        # If the deal has expired (4xx) fall through to fetch fresh content instead.
        if (task.get("kind") or "").lower() == "recycle":
            cand = _pick_recycle_item(task, context.get("recycle_candidates") or [])
            cand_url = cand.get("external_url") if cand else None
            deal_alive = await _verify_url_active(cand_url)

            if cand and deal_alive:
                # Valid recycle — reuse the break-out post.
                item = {
                    "title": cand.get("text_preview") or "Break-out hit",
                    "body_text": cand.get("text") or cand.get("text_preview") or "",
                    "external_url": None,
                    "topics": [],
                    "format_tag": task.get("format"),
                }
                post = await generate_post(item, task, context.get("channel_dna") or {})
                queued = await add_to_review_queue(channel_id, post, task, None)
                auto = await maybe_auto_publish(channel_id, queued["generated_post_id"])
                return {
                    "task_id": task_id,
                    "generated_post_id": queued["generated_post_id"],
                    "review_status": "approved" if auto.get("auto_published") else "pending",
                    "scheduled_at": queued["scheduled_at"],
                    "used_original": False,
                    "items_fetched": 0,
                    "items_passing": 0,
                    "auto_published": auto.get("auto_published"),
                }
            # Deal expired or no candidate → fall through to fresh source fetch below.

        # 1. gather items from all active sources
        category = ((context.get("channel_dna") or {}).get("category") or "").lower().strip()
        is_deals = category in {"deals", "shopping", "coupons", "offers"}
        sources = (await fetch_content_sources(channel_id, task.get("topic"), task.get("format")))["sources"]
        items: list[dict] = []

        # Deals channels: try LIVE Amazon/Flipkart product deals first (today's
        # deals, >=80% off preferred, never below 65%, affiliate-tagged). If that
        # yields nothing (e.g. the host's datacenter IP is blocked), fall through
        # to the active sources (grabon.in coupon pages).
        if is_deals:
            # The slot's topic is a CATEGORY chosen by the strategy (e.g. "Fashion
            # Women", "Headphones") — scrape THAT category so the day's mix matches
            # the plan, instead of always pulling the same few categories.
            live = await self._fetch_live_deals(sources, task.get("topic"))
            items.extend(live)
        elif task.get("topic"):
            # Non-deals channels (tech, entertainment, study, …): the slot's topic
            # is a THEME chosen by the strategy. Discover real on-theme content from
            # blogs/news + YouTube so the post links to current material, not an
            # invented one. Falls back to configured RSS/website sources below.
            try:
                from tools.content import discover_theme_content
                items.extend(await discover_theme_content(task.get("topic"), category))
            except Exception as exc:  # noqa: BLE001
                log.warning("theme discovery failed for %s: %s", task.get("topic"), exc)

        if not items:
            for src in sources:
                fetched = await self._fetch_from_source(src, task, channel_id, client, is_deals=is_deals)
                for it in fetched:
                    it["_source_id"] = src["id"]
                items.extend(fetched)

        # dedup against already-used URLs
        fresh: list[dict] = []
        for it in items:
            url = it.get("external_url")
            if url and (await check_url_used(channel_id, url))["already_used"]:
                continue
            fresh.append(it)

        dna = context.get("channel_dna") or {}
        used_original = False
        content_item_id = None

        # Deals aggregator: every current deal IS on-topic, so don't make scraped
        # deals pass article-style relevance scoring (brand names rarely match topic
        # keywords). Pick a deal — preferring one whose brand matches the slot topic —
        # and generate directly so the post always has a real deal + matching link.
        if is_deals and fresh:
            item = self._pick_deal_item(fresh, task.get("topic"))
            content_item_id = await save_content_item(channel_id, item.get("_source_id"), item)
            post = await generate_post(item, task, dna)
            queued = await add_to_review_queue(channel_id, post, task, content_item_id)
            auto = await maybe_auto_publish(channel_id, queued["generated_post_id"])
            return {
                "task_id": task_id, "generated_post_id": queued["generated_post_id"],
                "review_status": "approved" if auto.get("auto_published") else "pending",
                "scheduled_at": queued["scheduled_at"], "used_original": False,
                "items_fetched": len(items), "items_passing": len(fresh),
                "auto_published": auto.get("auto_published"),
            }

        # 2. score (relax threshold by 1 if nothing passes)
        result = score_content_items(fresh, context)
        scored = [s for s in result["scored_items"]]
        passing = [s for s in scored if s["scores"]["passed"]]
        if not passing and fresh:
            relaxed = dict(context)
            relaxed["score_threshold"] = max(1, context.get("score_threshold", 4) - 1)
            scored = score_content_items(fresh, relaxed)["scored_items"]
            passing = [s for s in scored if s["scores"]["passed"]]

        if passing:
            passing.sort(key=lambda s: s["scores"]["total"], reverse=True)
            top = passing[0]
            item = top["content_item"]
            content_item_id = await save_content_item(channel_id, item.get("_source_id"), item)
            await save_content_score(content_item_id, channel_id, top["scores"])
            if item.get("_source_id"):
                await update_source_quality_score(item["_source_id"], top["scores"]["total"])
            post = await generate_post(item, task, dna)
        else:
            # 3. fallback: original post on the topic
            used_original = True
            post = await generate_original_post(task, dna)

        queued = await add_to_review_queue(channel_id, post, task, content_item_id)
        auto = await maybe_auto_publish(channel_id, queued["generated_post_id"])
        return {
            "task_id": task_id,
            "generated_post_id": queued["generated_post_id"],
            "review_status": "approved" if auto.get("auto_published") else "pending",
            "scheduled_at": queued["scheduled_at"],
            "used_original": used_original,
            "items_fetched": len(items),
            "items_passing": len(passing),
            "auto_published": auto.get("auto_published"),
        }

    @staticmethod
    async def _fetch_live_deals(sources: list[dict], topic: str | None = None) -> list[dict]:
        """Scrape today's live product deals (affiliate-tagged) for the slot's
        category and adapt them to content items. ``topic`` is the strategy's
        category for this slot; we scrape that category specifically (falling back
        to the full set if it doesn't match or yields nothing). Returns [] on any
        failure so the caller falls back to grabon.in coupon pages."""
        from config import settings
        try:
            from tools.deal_scrapers import (
                get_fresh_deals, deal_to_content_item, resolve_deal_categories,
            )
            cats = resolve_deal_categories(topic) or None
            # Scrape a few per category so a single-category slot still has choices.
            per_cat = settings.DEAL_MAX_PER_CATEGORY if not cats else max(settings.DEAL_MAX_PER_CATEGORY, 4)
            deals = await get_fresh_deals(max_per_category=per_cat, categories=cats)
            if not deals and cats:
                # category had nothing today -> fall back to the full set
                deals = await get_fresh_deals(max_per_category=settings.DEAL_MAX_PER_CATEGORY)
        except Exception:
            return []
        src_id = sources[0]["id"] if sources else None
        out = []
        for d in deals:
            it = deal_to_content_item(d)
            # A deal with no real link is a dead end — skip it so we never post a
            # linkless "deal" (the reader can't act on it).
            if not it.get("external_url"):
                continue
            it["_source_id"] = src_id
            out.append(it)
        return out

    @staticmethod
    def _pick_deal_item(fresh: list[dict], topic: str | None) -> dict:
        """Choose a scraped deal — prefer one whose brand/title overlaps the slot
        topic so the post is on-theme; otherwise take the first fresh deal."""
        topic_words = {w for w in re.findall(r"[a-z0-9]+", (topic or "").lower()) if len(w) > 2}
        if topic_words:
            for it in fresh:
                title_words = set(re.findall(r"[a-z0-9]+", (it.get("title") or "").lower()))
                if topic_words & title_words:
                    return it
        return fresh[0]

    async def _fetch_from_source(self, src, task, channel_id, client, is_deals: bool = False) -> list[dict]:
        topic = task.get("topic")
        try:
            # Deals/coupons channels: scrape the site for INDIVIDUAL deal pages so
            # each post deep-links to that specific offer (not the homepage).
            if is_deals and src["type"] in ("rss", "website"):
                deals = await scrape_deal_links(src["url"], topic)
                if deals:
                    return deals
                # fall through to normal handling if no deal links were found
            if src["type"] == "rss":
                return fetch_rss_feed(src["url"], topic)["items"]
            if src["type"] == "website":
                return [await scrape_website(src["url"], topic)]
            if src["type"] == "telegram_channel" and client is not None:
                posts = (await get_channel_posts(client, src["url"], days=2))["posts"]
                return [{"title": (p.get("text") or "")[:120], "body_text": p.get("text"),
                         "external_url": None, "published_at": p.get("posted_at"),
                         "views": p.get("views"), "forwards": p.get("forwards"),
                         "reactions": p.get("reactions"), "format_tag": p.get("format")}
                        for p in posts]
        except Exception:
            return []
        return []

    def _summarize(self, result: dict[str, Any]) -> dict[str, Any]:
        return {k: result.get(k) for k in ("task_id", "used_original", "items_passing", "review_status")}


async def _main(task_id: str, with_telegram: bool) -> None:
    task = await get_strategy_task(task_id)
    if not task:
        raise SystemExit(f"strategy_task {task_id} not found")
    agent = ContentIntelligenceAgent()
    if with_telegram:
        async with telethon_session() as client:
            result = await agent.run(task["channel_id"], task_id=task_id, client=client)
    else:
        result = await agent.run(task["channel_id"], task_id=task_id)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Content Intelligence Agent for one slot")
    parser.add_argument("--task", required=True, help="strategy_task UUID")
    parser.add_argument("--telegram", action="store_true", help="enable telegram_channel sources")
    args = parser.parse_args()
    asyncio.run(_main(args.task, args.telegram))
