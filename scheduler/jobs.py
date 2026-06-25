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
    # Content is generated in-flow right after the plan (no per-slot dispatcher).
    await _safe(generate_content_for_strategy(cid, client), f"content/{uname}")


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
            # Generate the day's planned content in-flow (no per-slot dispatcher).
            await _safe(generate_content_for_strategy(cid, client), f"content/daily/{uname}")
    return {"channels": len(channels)}


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
        await _safe(seed_default_sources(channel_id, ctx.get("category"), posts=channel_posts), f"sources/{uname}")
        # Generate content for the whole plan up front (demo flow) so the Content
        # Factory is populated immediately — the scheduler no longer dispatches
        # content per-slot. Every planned slot (incl. retention triggers) ships a
        # real post in its strategy-given format.
        generated = await _safe(generate_content_for_strategy(channel_id, client), f"content/{uname}")
    await update_channel_meta(channel_id, status=ChannelStatus.active)
    return {"tier": tier, "pipeline": "full",
            "content_generated": (generated or {}).get("generated", 0)}


async def generate_content_for_strategy(channel_id: str, client=None, limit: int | None = None) -> dict:
    """Generate content for pending slots of a channel's active strategy.

    For ephemeral-content categories (deals, shopping, coupons) only slots within
    the next 2 days are generated — deals expire, so generating a week in advance
    produces stale content. The daily cycle regenerates each morning."""
    ctx = await get_channel_context(channel_id)
    category = (ctx.get("category") or "").lower().strip()
    days_ahead = 2 if category in EPHEMERAL_CATEGORIES else None
    tasks = await get_pending_tasks_for_channel(channel_id, days_ahead=days_ahead)
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
        if res:
            await mark_task_generated(task["id"], res.get("generated_post_id"))
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


async def _dispatch(due: list[dict], client) -> dict:
    n = 0
    for task in due:
        res = await _safe(
            ContentIntelligenceAgent().run(task["channel_id"], task_id=task["id"], client=client),
            f"content/{task['id']}",
        )
        if res:
            await mark_task_generated(task["id"], res.get("generated_post_id"))
            n += 1
    return {"dispatched": n}
