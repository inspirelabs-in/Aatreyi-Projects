"""Deal-slot executor — the Scheduler's per-slot worker for deals channels.

The Strategy Agent only PLANS slots (when / category / marketplace / loot|single /
media / why). This module is what the Scheduler runs when a slot's scrape moment
arrives:

    1. scrape fresh deals for the slot's assigned category (marketplace-specific)
    2. rank them (discount + category engagement + stock reachability + competitor
       trends) — tools.deal_ranking
    3. select the best candidate(s)
    4. build EXACTLY ONE caption with ONE CTA link
       (single = one product + photo; loot = many deals, no image)
    5. queue it for approval (auto-approved when the channel is autonomous)
    6. publish_due_posts publishes it AT the slot's scheduled time

It never runs on its own timer — the dispatcher (scheduler.jobs) calls it per due
slot, so scraping happens ~15-20 min before each post, not all at once.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from tools.content import add_to_review_queue, maybe_auto_publish, recent_title_fingerprints
from tools.deal_ranking import is_reachable, rank_deals
from tools.deal_scrapers import get_fresh_deals, resolve_deal_categories
from tools.loot_deals import build_loot_post, build_single_deal_post

log = logging.getLogger("deal_executor")


async def _record_deal_items(channel_id: str, used: list[dict]) -> None:
    """Persist the products actually used as ContentItems so the title/url de-dup
    blocks them from repeating within the no-repeat window."""
    from db.base import AsyncSessionLocal
    from db.models import ContentItem, ContentItemStatus

    if not used:
        return
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as s:
        for d in used:
            s.add(ContentItem(
                channel_id=cid,
                external_url=(d.get("affiliate_url") or d.get("product_url")),
                title=d.get("title"), format_tag="deal", status=ContentItemStatus.used,
            ))
        await s.commit()


async def execute_deal_slot(
    task: dict,
    preferred_categories: list[str] | None = None,
    trending_categories: set[str] | None = None,
) -> dict[str, Any] | None:
    """Execute one planned deal slot: scrape → rank → build one post → queue.

    `task` is a due-slot dict from get_due_tasks (kind, topic=category,
    marketplace, media_type, scheduled_date/time, id). Returns the queued-post
    info, or None when no genuine deal was found (the slot stays pending and the
    next dispatch retries — we never fabricate a deal to fill a slot)."""
    cid = task["channel_id"]
    kind = (task.get("kind") or "single").lower()
    category = task.get("topic")
    marketplace = task.get("marketplace")

    seen = await recent_title_fingerprints(cid)
    if kind == "loot":
        # LOOT: broad pull across all categories + both marketplaces → aggregate.
        deals = await get_fresh_deals()
        ranked = rank_deals(deals, preferred_categories=preferred_categories,
                            trending_categories=trending_categories)
        post = build_loot_post(ranked, seen) if ranked else None
    else:
        # SINGLE: scrape the assigned category+marketplace first (targeted, deeper
        # so ranking has real choices). A single category/marketplace often yields
        # just 1-2 deals past the discount floor, and that one may be a dupe or a
        # bogus >95% discount (dropped by the sanity cap) — so if the assignment is
        # dry, fall back to the marketplace's best deal from the broad (cached) pool.
        plat = marketplace or "Amazon"
        cats = resolve_deal_categories(category) or None
        deals = await get_fresh_deals(platforms=[plat], categories=cats, max_per_category=6)
        ranked = rank_deals(deals, preferred_categories=preferred_categories,
                            trending_categories=trending_categories, platform=plat)
        post = build_single_deal_post(ranked, plat, seen, prefer_ranked=True) if ranked else None
        if not post:
            broad = await get_fresh_deals()  # both marketplaces, all categories (cached)
            ranked = rank_deals(broad, preferred_categories=preferred_categories,
                                trending_categories=trending_categories, platform=plat)
            post = build_single_deal_post(ranked, plat, seen, prefer_ranked=True) if ranked else None
        # stock best-effort: only a definitive 404/410 drops the pick; retry once.
        if post and not await is_reachable(post.get("link_url") or ""):
            dead = {(d.get("title") or "") for d in post.get("used", [])}
            retry = [d for d in ranked if (d.get("title") or "") not in dead]
            post = build_single_deal_post(retry, plat, seen, prefer_ranked=True)
    if not post:
        log.info("deal slot %s: no fresh %s deal after ranking", task.get("id"), kind)
        return None

    # 4b. Strategy-context-aware caption for SINGLE-product posts: the Content
    #     Generator shapes headline/hook/CTA/emoji/urgency from DNA + today's
    #     strategy + this slot's reason + competitor intelligence (guidance, never
    #     copied), not from the deal alone. Loot stays a structured multi-deal list.
    #     Any failure → keep the template caption (pipeline never breaks).
    if kind == "single" and post.get("used"):
        try:
            from tools.content import generate_deal_caption
            from tools.strategy_context import build_strategy_context
            ctx = await build_strategy_context(cid)
            cap = await generate_deal_caption(post["used"][0], ctx, task.get("rationale"))
            if cap and cap.get("post_text"):
                post["post_text"] = cap["post_text"]
                post["cta"] = cap.get("cta") or post.get("cta")
        except Exception:
            pass

    # 5. queue for approval (auto-approved when the channel is autonomous). The
    #    slot's scheduled_at makes publish_due_posts send it AT its planned time.
    gp_payload = {
        "post_text": post.get("post_text"),
        "format": post.get("post_format", "text"),
        "media_url": post.get("media_url"),
        "link_url": post.get("link_url"),
        "cta": post.get("cta"),
        "llm_model": None,
        "generation_prompt": task.get("rationale"),
    }
    queue_task = {
        "id": task["id"],
        "scheduled_date": task.get("scheduled_date"),
        "scheduled_time": task.get("scheduled_time"),
        "format": post.get("post_format", "text"),
    }
    queued = await add_to_review_queue(cid, gp_payload, queue_task)
    await maybe_auto_publish(cid, queued["generated_post_id"])
    await _record_deal_items(cid, post.get("used") or [])
    log.info("deal slot %s queued (%s, %s) scheduled_at=%s",
             task.get("id"), kind, marketplace or "-", queued.get("scheduled_at"))
    return {"generated_post_id": queued["generated_post_id"],
            "kind": kind, "used": len(post.get("used") or [])}
