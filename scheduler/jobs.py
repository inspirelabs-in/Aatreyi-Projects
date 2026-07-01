"""Scheduler job functions — tier-aware orchestration.

Channel pipelines differ by tier (workflow.md):
    Tier A  (new, <5k subs):   Competitor -> Strategy            (no DNA, no Analytics)
    Tier B/C (mid/established): DNA -> Competitor -> Analytics -> Strategy

`detect_tier` decides routing; tier is refreshed from live member count at the
start of each full cycle, so a Tier-A channel graduates to B/C automatically
once it crosses 5k subscribers.

Per-channel failures are isolated (logged via agent_runs). Agents and the
telethon session are referenced at module level so tests can monkeypatch them.
"""
from __future__ import annotations

import logging

from config import settings
from agents.analytics import AnalyticsAgent
from agents.channel_dna import ChannelDNAAgent
from agents.competitor_intelligence import CompetitorIntelligenceAgent
from agents.content_intelligence import ContentIntelligenceAgent
from agents.strategy import StrategyAgent
from db.models import ChannelStatus
from tools.channel_dna import MIN_POSTS_AGENT_GATE, detect_tier
from tools.channels import (
    clear_strategy_review_flag,
    get_channel_context,
    has_valid_dna,
    list_channels,
    update_channel_meta,
)
from tools.shared import get_channel_posts, get_telegram_channel_info
from tools.competitor import refresh_competitor_posts_for_channel
from tools.strategy import get_due_tasks, get_pending_tasks_for_channel, mark_task_generated
from tools.telegram_client import telethon_session

log = logging.getLogger("scheduler.jobs")

TIER_A = "new"  # Tier A == new channel (<5k); mid/established == Tier B/C

# Categories where content has an expiry (deals, coupons, etc.).
# For these, content is only generated 2 days in advance so posts are always fresh.
EPHEMERAL_CATEGORIES = {"deals", "shopping", "coupons", "offers"}

# cadence label -> (snapshot_type, agent trigger)
_CADENCE = {
    "weekly": ("weekly", "cron_weekly"),
    "monthly": ("monthly", "cron_monthly"),
}


async def _safe(coro, label: str):
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        log.warning("%s failed: %s: %s", label, type(exc).__name__, exc)
        return None


def is_tier_a(tier: str | None) -> bool:
    return (tier or TIER_A) == TIER_A


async def _refresh_tier(cid: str, uname: str, client) -> str:
    """Fetch live member count, re-classify tier, persist it. Returns the tier."""
    info = await get_telegram_channel_info(client, uname)
    tier = detect_tier(info.get("member_count"))
    await update_channel_meta(
        cid, tier=tier, telegram_id=info.get("channel_id"), display_name=info.get("title")
    )
    return tier


async def _has_enough_history(uname: str, client) -> bool:
    """True if the channel has accumulated enough posts to profile/analyse."""
    try:
        res = await get_channel_posts(client, uname, days=30, limit=MIN_POSTS_AGENT_GATE + 5)
        return res.get("total_fetched", 0) >= MIN_POSTS_AGENT_GATE
    except Exception:
        return False


async def _should_run_full(tier: str, uname: str, client) -> bool:
    """Mid/established channels always run the full pipeline (DNA → Competitor → Analytics → Strategy).
    New (Tier-A) channels start lean until they accumulate enough recent post history."""
    if not is_tier_a(tier):
        return True
    return await _has_enough_history(uname, client)


# ── Full cycle (weekly / monthly), tier + data-aware ─────────────────────────
async def _run_full_cycle_for(cid, uname, tier, client, cadence: str) -> None:
    snapshot_type, trig = _CADENCE[cadence]
    if await _should_run_full(tier, uname, client):
        # Full pipeline: B/C, or a Tier-A channel that now has enough history.
        await _safe(ChannelDNAAgent(trig).run(cid, username=uname, client=client), f"dna/{uname}")
        await _safe(CompetitorIntelligenceAgent(trig).run(cid, client=client), f"competitor/{uname}")
        await _safe(AnalyticsAgent(snapshot_type, trigger=trig).run(cid, username=uname, client=client), f"analytics/{uname}")
        await _safe(StrategyAgent(snapshot_type).run(cid), f"strategy/{uname}")
    else:
        # Lean path — brand-new Tier-A channel: discover competitors, then plan.
        await _safe(CompetitorIntelligenceAgent(trig).run(cid, client=client), f"competitor/{uname}")
        await _safe(StrategyAgent(snapshot_type).run(cid), f"strategy/{uname}")
    # Content is NOT generated here anymore — the per-slot JIT dispatcher
    # (dispatch_due_content) generates each post ~15-20 min before its slot time,
    # then publish_due_posts publishes it AT the slot time. This builds the dated
    # plan now; posts fill in on schedule.


async def run_weekly_cycle() -> dict:
    channels = await list_channels()
    log.info("weekly cycle: %d channels", len(channels))
    async with telethon_session() as client:
        for ch in channels:
            cid, uname = ch["id"], ch["telegram_username"]
            tier = await _safe(_refresh_tier(cid, uname, client), f"tier/{uname}") or ch.get("tier")
            await _run_full_cycle_for(cid, uname, tier, client, "weekly")
    return {"channels": len(channels)}


async def run_monthly_audit() -> dict:
    channels = await list_channels()
    log.info("monthly audit: %d channels", len(channels))
    async with telethon_session() as client:
        for ch in channels:
            cid, uname = ch["id"], ch["telegram_username"]
            tier = await _safe(_refresh_tier(cid, uname, client), f"tier/{uname}") or ch.get("tier")
            await _run_full_cycle_for(cid, uname, tier, client, "monthly")
    return {"channels": len(channels)}


# ── Daily cycle (uses stored tier; refreshed weekly) ─────────────────────────
async def run_daily_cycle() -> dict:
    channels = await list_channels()
    log.info("daily cycle: %d channels", len(channels))
    async with telethon_session() as client:
        for ch in channels:
            cid, uname, tier = ch["id"], ch["telegram_username"], ch.get("tier")
            # Run daily analytics for B/C, and for any Tier-A channel that has
            # already earned a valid DNA profile (i.e. enough history).
            if not is_tier_a(tier) or await has_valid_dna(cid):
                await _safe(
                    AnalyticsAgent("daily").run(cid, username=uname, client=client),
                    f"analytics/daily/{uname}",
                )
            # Refresh competitor posts daily — tracks what rivals posted today
            # and which posts are getting the most reactions, so strategy stays current.
            await _safe(refresh_competitor_posts_for_channel(cid, client), f"comp_refresh/daily/{uname}")
            await _safe(StrategyAgent("daily").run(cid), f"strategy/daily/{uname}")
            if ch.get("needs_strategy_review"):
                await _safe(StrategyAgent("daily", trigger="manual").run(cid), f"strategy/review/{uname}")
                await clear_strategy_review_flag(cid)
            # Content is generated per-slot (JIT) by dispatch_due_content ~15-20 min
            # before each slot and published at the slot time — not bulk-generated here.
    return {"channels": len(channels)}


# ── Daily deals refresh (deals-aggregator channels) ──────────────────────────
async def run_daily_deals() -> dict:
    """Refresh deals-category channels with TODAY's deals every day.

    Builds a fresh daily plan and generates content — which, for deals channels,
    pulls today's live Amazon/Flipkart product deals (>=80% off preferred, never
    below 65%, affiliate-tagged), falling back to grabon.in coupon pages."""
    channels = await list_channels()
    deals_channels = [c for c in channels if (c.get("category") or "").lower() in EPHEMERAL_CATEGORIES]
    log.info("daily deals refresh: %d deals channels", len(deals_channels))
    async with telethon_session() as client:
        for ch in deals_channels:
            cid, uname = ch["id"], ch["telegram_username"]
            # Refresh the daily plan (incl. GrabOn's 50 executable slots); content
            # is generated per-slot (JIT) by dispatch_due_content — scraped, ranked
            # and captioned at scrape_at — and published at each slot's time.
            await _safe(StrategyAgent("daily").run(cid), f"deals_strategy/{uname}")
    return {"deals_channels": len(deals_channels)}


# NOTE: The old `run_grabon_deals` interval auto-poster was removed. GrabOn is now
# fully slot-driven: the Strategy Agent PLANS 50 executable slots/day (loot + single,
# each with scrape_at / marketplace / media / rationale) and the per-slot dispatcher
# (dispatch_due_content → _dispatch → tools.deal_executor.execute_deal_slot) scrapes,
# ranks, writes ONE caption, queues for approval, and publish_due_posts sends it at
# the slot's time. One coherent pipeline instead of an interval poster.


# ── Onboarding orchestrator (tier-aware initial run) ─────────────────────────
async def onboard_channel_pipeline(channel_id: str) -> dict:
    """Run the initial pipeline for a freshly added channel.

    Onboarding ALWAYS runs the full pipeline (DNA → Competitor → Analytics).
    The post-history gate (_should_run_full) is for recurring scheduled cycles
    only — at onboarding time we always want a complete initial profile.
    """
    ctx = await get_channel_context(channel_id)
    uname = ctx.get("username")
    if not uname:
        raise ValueError(f"channel {channel_id} not found")
    async with telethon_session() as client:
        tier = await _refresh_tier(channel_id, uname, client)
        await _safe(ChannelDNAAgent("manual").run(channel_id, username=uname, client=client), f"dna/{uname}")
        await _safe(CompetitorIntelligenceAgent("manual").run(channel_id, client=client), f"competitor/{uname}")
        await _safe(AnalyticsAgent("daily", trigger="manual").run(channel_id, username=uname, client=client), f"analytics/{uname}")
        # Fetch posts once — reused for backfill AND source auto-detection.
        channel_info = await _safe(get_telegram_channel_info(client, uname), f"info/{uname}") or {}
        channel_posts = (await _safe(get_channel_posts(client, uname, days=30), f"posts/{uname}") or {}).get("posts", [])
        # Backfill a REAL daily analytics history from the channel's actual posts
        # so the dashboard/analytics aren't empty on day 1 (real ER + intelligence).
        await _safe(_backfill_history_with_data(channel_id, channel_posts, channel_info.get("member_count")), f"backfill/{uname}")
        await _safe(StrategyAgent("weekly").run(channel_id), f"strategy/{uname}")
        from tools.content_sources import seed_default_sources
        # Pass posts so source seeder can detect the channel's primary website
        # (e.g. grbn.in links → grabon.in) instead of using a generic category default.
        await _safe(seed_default_sources(channel_id, ctx.get("category"), posts=channel_posts, bio_text=channel_info.get("description")), f"sources/{uname}")
        # Seed just the next couple of due slots so the channel isn't empty right
        # after onboarding; the rest are generated per-slot (JIT) ~15-20 min before
        # their time and published at the slot time. NOT a full-day bulk generate.
        generated = await _safe(generate_content_for_strategy(channel_id, client, limit=2), f"content/{uname}")
    await update_channel_meta(channel_id, status=ChannelStatus.active)
    return {"tier": tier, "pipeline": "full",
            "content_generated": (generated or {}).get("generated", 0)}


async def generate_content_for_strategy(channel_id: str, client=None, limit: int | None = None) -> dict:
    """Generate content for the channel's active strategy — TODAY's slots only.

    The strategy still plans the whole period (the dated week is visible in the
    UI), but we only generate posts for slots scheduled today (plus any overdue
    pending ones), for EVERY channel. The daily cycle runs each morning and
    generates that day's slots — so content is always fresh and we never burn
    LLM calls generating a week of posts in advance that may go stale."""
    # days_ahead=0 -> cutoff is today -> only slots scheduled on/before today.
    tasks = await get_pending_tasks_for_channel(channel_id, days_ahead=0)
    if limit:
        tasks = tasks[:limit]
    if not tasks:
        return {"generated": 0}
    log.info("generating content for %d slots of channel %s", len(tasks), channel_id)
    n = 0
    for task in tasks:
        res = await _safe(
            ContentIntelligenceAgent().run(channel_id, task_id=task["id"], client=client),
            f"content/{task['id']}",
        )
        # Only mark a slot generated when a real post was created. Deals slots that
        # found no real deal are skipped (no generated_post_id) and stay pending so
        # the next cycle retries — we never fabricate to "fill" a slot.
        if res and res.get("generated_post_id"):
            await mark_task_generated(task["id"], res["generated_post_id"])
            n += 1
    return {"generated": n}


async def _backfill_history(channel_id: str, uname: str, client) -> int:
    from tools.analytics import save_real_daily_history
    info = await get_telegram_channel_info(client, uname)
    posts = (await get_channel_posts(client, uname, days=30))["posts"]
    return await save_real_daily_history(channel_id, posts, info.get("member_count"))


async def _backfill_history_with_data(channel_id: str, posts: list, member_count: int | None) -> int:
    from tools.analytics import save_real_daily_history
    return await save_real_daily_history(channel_id, posts, member_count)


# ── Subscriber poll (every ~20 min) — near-real-time growth/churn ────────────
async def poll_subscribers() -> dict:
    from tools.subscribers import record_subscriber_reading

    channels = await list_channels()
    n = 0
    async with telethon_session() as client:
        for ch in channels:
            uname = ch["telegram_username"]
            info = await _safe(get_telegram_channel_info(client, uname), f"subpoll/{uname}")
            if info and info.get("member_count") is not None:
                await record_subscriber_reading(ch["id"], info["member_count"])
                n += 1
    log.info("subscriber poll: sampled %d channels", n)
    return {"sampled": n}


# ── Content-slot dispatcher (every 5 min) ────────────────────────────────────
async def dispatch_content_slots(lead_minutes: int = 30) -> dict:
    due = await get_due_tasks(lead_minutes)
    if not due:
        return {"dispatched": 0}
    log.info("dispatching %d content slots", len(due))
    try:
        async with telethon_session() as client:
            return await _dispatch(due, client)
    except Exception:
        return await _dispatch(due, None)


_DEAL_KINDS = {"loot", "single"}


async def _dispatch(due: list[dict], client) -> dict:
    from tools.deal_executor import execute_deal_slot
    from tools.strategy import get_deal_ranking_context

    n = 0
    ranking_ctx: dict[str, dict] = {}  # per-channel cache
    for task in due:
        kind = (task.get("kind") or "").lower()
        if kind in _DEAL_KINDS:
            # Deal slot: the Scheduler scrapes + ranks + writes ONE caption itself
            # (the Strategy Agent only planned the slot).
            cid = task["channel_id"]
            if cid not in ranking_ctx:
                ranking_ctx[cid] = await _safe(get_deal_ranking_context(cid), f"rankctx/{cid}") or {}
            ctx = ranking_ctx[cid]
            res = await _safe(
                execute_deal_slot(
                    task,
                    preferred_categories=ctx.get("preferred_categories"),
                    trending_categories=set(ctx.get("trending_categories") or []),
                ),
                f"deal_slot/{task['id']}",
            )
        else:
            res = await _safe(
                ContentIntelligenceAgent().run(task["channel_id"], task_id=task["id"], client=client),
                f"content/{task['id']}",
            )
        if res and res.get("generated_post_id"):
            await mark_task_generated(task["id"], res["generated_post_id"])
            n += 1
    return {"dispatched": n}


async def dispatch_due_content() -> dict:
    """JIT generation: generate content for slots whose time is within the lead
    window (~15-20 min out). Registered on an interval so posts are prepared just
    before their slot — never all at once."""
    return await dispatch_content_slots(lead_minutes=settings.CONTENT_GENERATION_LEAD_MIN)


async def publish_due_posts() -> dict:
    """Publish approved posts whose slot time has arrived (scheduled_at <= now).

    Generation happens ~15-20 min earlier (dispatch_due_content); this makes the
    post go out AT its planned time. Manual-review channels are unaffected (their
    posts are only approved when the operator approves)."""
    from datetime import datetime, timezone
    from sqlalchemy import select
    from db.base import AsyncSessionLocal
    from db.models import GeneratedPost, PostQueue, QueueStatus, ReviewStatus, Channel
    from tools.content import publish_generated_post
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(PostQueue.generated_post_id, Channel.telegram_username)
            .join(GeneratedPost, PostQueue.generated_post_id == GeneratedPost.id)
            .join(Channel, GeneratedPost.channel_id == Channel.id)
            .where(PostQueue.status == QueueStatus.queued,
                   GeneratedPost.review_status == ReviewStatus.approved,
                   PostQueue.scheduled_at <= now)
            .order_by(PostQueue.scheduled_at.asc())
            .limit(25)
        )).all()
    n = 0
    for gp_id, uname in rows:
        res = await _safe(publish_generated_post(str(gp_id), uname), f"publish/{gp_id}")
        if res and res.get("published"):
            n += 1
    if n:
        log.info("published %d due post(s)", n)
    return {"published": n}
