"""Phase 8 — Scheduler: job registration, due-slot selection, orchestration order."""
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, StrategyTask, TaskStatus
from tools.channels import get_or_create_channel
from tools.strategy import LOCAL_TZ, get_due_tasks, save_strategy


def test_build_scheduler_registers_all_jobs():
    from scheduler.main import build_scheduler

    sched = build_scheduler()
    ids = {j.id for j in sched.get_jobs()}
    # content_dispatcher is intentionally NOT registered — content is generated
    # in-flow right after each strategy build (onboarding + daily/weekly cycles).
    assert ids == {"daily_cycle", "weekly_cycle", "monthly_audit", "subscriber_poll"}


@pytest.mark.asyncio
async def test_get_due_tasks_window():
    channel = await get_or_create_channel("sched_due_channel")
    cid = channel["id"]
    now = datetime.now(LOCAL_TZ)
    today = now.date().isoformat()
    soon = (now + timedelta(minutes=10)).strftime("%H:%M")
    later = (now + timedelta(minutes=90)).strftime("%H:%M")
    try:
        await save_strategy(cid, {
            "strategy_type": "daily",
            "period_start": today, "period_end": today,
            "goal": "g", "post_frequency_per_day": 2, "content_mix": [{"format": "text", "pct": 100}],
            "primary_topics": ["x"],
            "tasks": [
                {"scheduled_date": today, "scheduled_time": soon, "format": "text", "topic": "x"},
                {"scheduled_date": today, "scheduled_time": later, "format": "text", "topic": "x"},
            ],
        })
        due = await get_due_tasks(lead_minutes=30)
        due_for_me = [d for d in due if d["channel_id"] == cid]
        assert len(due_for_me) == 1  # only the +10min slot is within 30-min window
    finally:
        async with AsyncSessionLocal() as s:
            ch = (await s.execute(select(Channel).where(Channel.id == cid))).scalar_one()
            await s.delete(ch)
            await s.commit()


def _fake_agent(name, calls):
    class _Fake:
        def __init__(self, *a, **k):
            pass

        async def run(self, channel_id, **kw):
            calls.append((channel_id, name))
            return {"generated_post_id": None}  # None avoids FK; real agent returns a valid id
    return _Fake


@asynccontextmanager
async def _fake_session():
    yield None


def _fake_info(member_count):
    async def _f(client, username):
        return {"member_count": member_count, "channel_id": 123, "title": "T",
                "has_disappearing_messages": False}
    return _f


def _fake_posts(n):
    async def _f(client, username, days=30, limit=500):
        return {"posts": [{} for _ in range(n)], "total_fetched": n}
    return _f


def _patch_jobs(monkeypatch, jobs, calls, channel):
    """Common patching: isolate to one channel, no network."""
    monkeypatch.setattr(jobs, "telethon_session", _fake_session)
    monkeypatch.setattr(jobs, "ChannelDNAAgent", _fake_agent("dna", calls))
    monkeypatch.setattr(jobs, "CompetitorIntelligenceAgent", _fake_agent("competitor", calls))
    monkeypatch.setattr(jobs, "AnalyticsAgent", _fake_agent("analytics", calls))
    monkeypatch.setattr(jobs, "StrategyAgent", _fake_agent("strategy", calls))

    async def _only_this(active_only=False):
        return [channel]
    monkeypatch.setattr(jobs, "list_channels", _only_this)


@pytest.mark.asyncio
async def test_weekly_cycle_tier_bc_full_pipeline(monkeypatch):
    import scheduler.jobs as jobs

    ch = await get_or_create_channel("sched_bc_channel")
    cid = ch["id"]
    calls: list = []
    chan = {"id": cid, "telegram_username": "sched_bc_channel", "tier": "mid", "needs_strategy_review": False}
    _patch_jobs(monkeypatch, jobs, calls, chan)
    monkeypatch.setattr(jobs, "get_telegram_channel_info", _fake_info(20000))  # -> mid (B/C)
    monkeypatch.setattr(jobs, "get_channel_posts", _fake_posts(120))           # has post history -> DNA runs
    try:
        await jobs.run_weekly_cycle()
        assert [n for c, n in calls if c == cid] == ["dna", "competitor", "analytics", "strategy"]
    finally:
        await _cleanup(cid)


@pytest.mark.asyncio
async def test_weekly_cycle_tier_a_no_history_is_lean(monkeypatch):
    import scheduler.jobs as jobs

    ch = await get_or_create_channel("sched_a_channel")
    cid = ch["id"]
    calls: list = []
    chan = {"id": cid, "telegram_username": "sched_a_channel", "tier": "new", "needs_strategy_review": False}
    _patch_jobs(monkeypatch, jobs, calls, chan)
    monkeypatch.setattr(jobs, "get_telegram_channel_info", _fake_info(1000))  # new (Tier A)
    monkeypatch.setattr(jobs, "get_channel_posts", _fake_posts(3))            # too few posts
    try:
        await jobs.run_weekly_cycle()
        mine = [n for c, n in calls if c == cid]
        assert mine == ["competitor", "strategy"]  # lean: NO dna, NO analytics
    finally:
        await _cleanup(cid)


@pytest.mark.asyncio
async def test_weekly_cycle_tier_a_with_history_runs_full(monkeypatch):
    import scheduler.jobs as jobs

    ch = await get_or_create_channel("sched_a_hist_channel")
    cid = ch["id"]
    calls: list = []
    chan = {"id": cid, "telegram_username": "sched_a_hist_channel", "tier": "new", "needs_strategy_review": False}
    _patch_jobs(monkeypatch, jobs, calls, chan)
    monkeypatch.setattr(jobs, "get_telegram_channel_info", _fake_info(1000))  # still Tier A by subs
    monkeypatch.setattr(jobs, "get_channel_posts", _fake_posts(25))           # enough history!
    try:
        await jobs.run_weekly_cycle()
        mine = [n for c, n in calls if c == cid]
        assert mine == ["dna", "competitor", "analytics", "strategy"]  # full despite <5k subs
    finally:
        await _cleanup(cid)


@pytest.mark.asyncio
async def test_onboarding_routes_by_tier(monkeypatch):
    import scheduler.jobs as jobs

    ch = await get_or_create_channel("sched_onboard_channel")
    cid = ch["id"]
    calls: list = []
    monkeypatch.setattr(jobs, "telethon_session", _fake_session)
    monkeypatch.setattr(jobs, "ChannelDNAAgent", _fake_agent("dna", calls))
    monkeypatch.setattr(jobs, "CompetitorIntelligenceAgent", _fake_agent("competitor", calls))
    monkeypatch.setattr(jobs, "AnalyticsAgent", _fake_agent("analytics", calls))
    monkeypatch.setattr(jobs, "StrategyAgent", _fake_agent("strategy", calls))
    monkeypatch.setattr(jobs, "get_telegram_channel_info", _fake_info(80000))  # -> established (B/C)
    monkeypatch.setattr(jobs, "get_channel_posts", _fake_posts(120))           # has posts -> full (DNA first)
    try:
        result = await jobs.onboard_channel_pipeline(cid)
        assert result["pipeline"] == "full"
        assert [n for c, n in calls if c == cid] == ["dna", "competitor", "analytics", "strategy"]
    finally:
        await _cleanup(cid)


@pytest.mark.asyncio
async def test_onboarding_no_posts_starts_lean(monkeypatch):
    # Criterion: post count (not subscribers) decides DNA. A large channel with
    # no posts skips DNA and starts with competitors.
    import scheduler.jobs as jobs

    ch = await get_or_create_channel("sched_nopost_channel")
    cid = ch["id"]
    calls: list = []
    monkeypatch.setattr(jobs, "telethon_session", _fake_session)
    monkeypatch.setattr(jobs, "ChannelDNAAgent", _fake_agent("dna", calls))
    monkeypatch.setattr(jobs, "CompetitorIntelligenceAgent", _fake_agent("competitor", calls))
    monkeypatch.setattr(jobs, "AnalyticsAgent", _fake_agent("analytics", calls))
    monkeypatch.setattr(jobs, "StrategyAgent", _fake_agent("strategy", calls))
    monkeypatch.setattr(jobs, "get_telegram_channel_info", _fake_info(80000))  # big channel
    monkeypatch.setattr(jobs, "get_channel_posts", _fake_posts(0))             # but no posts
    try:
        result = await jobs.onboard_channel_pipeline(cid)
        assert result["pipeline"] == "lean"
        assert [n for c, n in calls if c == cid] == ["competitor", "strategy"]  # NO dna/analytics
    finally:
        await _cleanup(cid)


async def _cleanup(cid):
    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == cid))).scalar_one()
        await s.delete(ch)
        await s.commit()


@pytest.mark.asyncio
async def test_dispatch_keeps_pending_on_failure(monkeypatch):
    import scheduler.jobs as jobs

    channel = await get_or_create_channel("sched_fail_dispatch")
    cid = channel["id"]
    now = datetime.now(LOCAL_TZ)
    today = now.date().isoformat()
    soon = (now + timedelta(minutes=10)).strftime("%H:%M")

    class _FailAgent:
        def __init__(self, *a, **k):
            pass

        async def run(self, channel_id, **kw):
            raise RuntimeError("generation failed")

    monkeypatch.setattr(jobs, "telethon_session", _fake_session)
    monkeypatch.setattr(jobs, "ContentIntelligenceAgent", _FailAgent)
    try:
        await save_strategy(cid, {
            "strategy_type": "daily",
            "period_start": today, "period_end": today,
            "goal": "g", "post_frequency_per_day": 1, "content_mix": [{"format": "text", "pct": 100}],
            "primary_topics": ["x"],
            "tasks": [{"scheduled_date": today, "scheduled_time": soon, "format": "text", "topic": "x"}],
        })
        result = await jobs.dispatch_content_slots(lead_minutes=30)
        assert result["dispatched"] == 0

        async with AsyncSessionLocal() as s:
            tasks = (await s.execute(select(StrategyTask).where(StrategyTask.channel_id == __import__("uuid").UUID(cid)))).scalars().all()
            assert tasks and tasks[0].status == TaskStatus.pending
    finally:
        async with AsyncSessionLocal() as s:
            ch = (await s.execute(select(Channel).where(Channel.id == cid))).scalar_one()
            await s.delete(ch)
            await s.commit()


@pytest.mark.asyncio
async def test_dispatch_marks_task_generated(monkeypatch):
    import scheduler.jobs as jobs

    channel = await get_or_create_channel("sched_dispatch_channel")
    cid = channel["id"]
    now = datetime.now(LOCAL_TZ)
    today = now.date().isoformat()
    soon = (now + timedelta(minutes=10)).strftime("%H:%M")

    calls: list = []
    monkeypatch.setattr(jobs, "telethon_session", _fake_session)
    monkeypatch.setattr(jobs, "ContentIntelligenceAgent", _fake_agent("content", calls))
    try:
        await save_strategy(cid, {
            "strategy_type": "daily",
            "period_start": today, "period_end": today,
            "goal": "g", "post_frequency_per_day": 1, "content_mix": [{"format": "text", "pct": 100}],
            "primary_topics": ["x"],
            "tasks": [{"scheduled_date": today, "scheduled_time": soon, "format": "text", "topic": "x"}],
        })
        result = await jobs.dispatch_content_slots(lead_minutes=30)
        assert result["dispatched"] >= 1

        async with AsyncSessionLocal() as s:
            tasks = (await s.execute(select(StrategyTask).where(StrategyTask.channel_id == __import__("uuid").UUID(cid)))).scalars().all()
            assert tasks and tasks[0].status == TaskStatus.generated
    finally:
        async with AsyncSessionLocal() as s:
            ch = (await s.execute(select(Channel).where(Channel.id == cid))).scalar_one()
            await s.delete(ch)
            await s.commit()


@pytest.mark.asyncio
async def test_generate_content_for_strategy_generates_all_pending_slots(monkeypatch):
    # Flow-driven generation (replaces the per-slot dispatcher): every pending
    # slot of the active strategy ships a post — regardless of slot time.
    import scheduler.jobs as jobs

    channel = await get_or_create_channel("sched_flow_channel")
    cid = channel["id"]
    today = datetime.now(LOCAL_TZ).date().isoformat()

    calls: list = []
    monkeypatch.setattr(jobs, "ContentIntelligenceAgent", _fake_agent("content", calls))
    try:
        await save_strategy(cid, {
            "strategy_type": "weekly",
            "period_start": today, "period_end": today,
            "goal": "g", "post_frequency_per_day": 3, "content_mix": [{"format": "text", "pct": 100}],
            "primary_topics": ["x"],
            "tasks": [
                {"scheduled_date": today, "scheduled_time": "09:00", "format": "poll", "topic": "x"},
                {"scheduled_date": today, "scheduled_time": "13:00", "format": "link", "topic": "y"},
                {"scheduled_date": today, "scheduled_time": "18:00", "format": "photo", "topic": "z"},
            ],
        })
        result = await jobs.generate_content_for_strategy(cid)
        assert result["generated"] == 3
        assert [n for c, n in calls if c == cid] == ["content", "content", "content"]

        async with AsyncSessionLocal() as s:
            tasks = (await s.execute(select(StrategyTask).where(StrategyTask.channel_id == __import__("uuid").UUID(cid)))).scalars().all()
            assert tasks and all(t.status == TaskStatus.generated for t in tasks)
    finally:
        async with AsyncSessionLocal() as s:
            ch = (await s.execute(select(Channel).where(Channel.id == cid))).scalar_one()
            await s.delete(ch)
            await s.commit()
