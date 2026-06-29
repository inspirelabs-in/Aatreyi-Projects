"""Phase 5 — Strategy computation + persistence + full agent run (no Telegram)."""
import uuid

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, CronJob, Strategy, StrategyStatus, StrategyTask
from tools.channels import get_or_create_channel
from tools.strategy import (
    build_growth_tactics,
    compute_content_mix,
    compute_strategy,
    get_active_strategy,
    get_competitor_gap_topics,
    greedy_select_slots,
    recommended_frequency,
)


def test_recommended_frequency_clip_and_boost():
    assert recommended_frequency(2.0, 12, 5.0) == 3.0          # +1.0 growth boost
    assert recommended_frequency(2.0, 7, 5.0) == 2.5           # +0.5 boost
    assert recommended_frequency(2.0, 1, 1.0) == 1.5           # -0.5 ER penalty
    assert recommended_frequency(10.0, 20, 9.0) == 5.0         # hard cap 5
    assert recommended_frequency(0.2, None, None) == 1.0       # floor 1


def test_content_mix_poll_rule_on_low_er():
    fmts = [{"format": "article", "share": 0.7}, {"format": "meme", "share": 0.3}]
    mix = compute_content_mix(fmts, None, None, avg_er=2.0)  # ER<3 -> poll 40%
    by = {m["format"]: m["pct"] for m in mix}
    assert by.get("poll") == 40
    assert sum(by.values()) == 100


def test_content_mix_holds_when_er_high():
    fmts = [{"format": "article", "share": 0.6}, {"format": "poll", "share": 0.4}]
    mix = compute_content_mix(fmts, None, None, avg_er=9.0)
    by = {m["format"]: m["pct"] for m in mix}
    assert sum(by.values()) == 100
    assert by["article"] > by["poll"]


def test_greedy_slots_respect_min_gap():
    scores = {h: 1.0 for h in range(24)}
    slots = greedy_select_slots(scores, n=3, min_gap=3)
    assert len(slots) == 3
    for a, b in zip(slots, slots[1:]):
        assert b - a >= 3


def test_gap_topics_excludes_category_labels_and_owned():
    # Bare category labels (tech/crypto/finance) are NOT content topics — they
    # must be filtered so an off-niche competitor set can't pollute the plan.
    my = {"tech", "ai"}
    comps = [{"top_themes": ["tech", "crypto"]}, {"top_themes": ["finance"]}]
    assert get_competitor_gap_topics(my, comps) == []
    # Specific, non-category themes DO survive as gaps.
    specific = [{"top_themes": ["amazon electronics deals", "tech"]}]
    gaps = get_competitor_gap_topics(my, specific)
    assert "amazon electronics deals" in gaps
    assert "tech" not in gaps  # owned + category label


def test_churn_executes_retention_and_reduces_cadence():
    from tools.analytics import classify_churn_risk
    # graded churn classification
    assert classify_churn_risk(None, False) == "unknown"
    assert classify_churn_risk(1.0, False) == "none"
    assert classify_churn_risk(-0.2, False) == "low"
    assert classify_churn_risk(-1.0, False) == "medium"
    assert classify_churn_risk(-3.0, False) == "high"
    assert classify_churn_risk(-0.1, True) == "high"  # spike signal overrides

    # on churn, the plan ACTS: a re-engagement poll is scheduled + cadence drops
    inputs = {
        "dna": {"post_frequency_per_day": 3.0, "avg_er": 4.0, "best_post_hour": 12,
                "category": "tech", "top_topics": ["AI"]},
        "analytics_daily": {"subscriber_delta_pct": -3, "subscriber_delta": -500, "churn_signal": True},
        "competitors": [],
    }
    s = compute_strategy(inputs, strategy_type="daily")
    assert any("re-engagement" in (t.get("topic") or "").lower() for t in s["tasks"]), "retention slot injected"
    assert s["tasks"][0]["format"] == "poll"  # retention poll is first
    # declining -> reduce_frequency executed (base 3.0 minus 1 = 2.0, no growth boost)
    assert s["post_frequency_per_day"] == 2.0
    kinds = {t["tactic"] for t in s["growth_tactics"]}
    assert {"re_engage", "reduce_frequency"} <= kinds


def test_silent_community_triggers_retention():
    inputs = {
        "dna": {"post_frequency_per_day": 2.0, "avg_er": 5.0, "best_post_hour": 12,
                "category": "tech", "top_topics": ["AI"]},
        "analytics_daily": {"subscriber_delta_pct": 0.5, "subscriber_delta": 10, "churn_signal": False},
        "community_state": "silent",
        "competitors": [],
    }
    s = compute_strategy(inputs, strategy_type="daily")
    assert any(t.get("kind") == "reengage" for t in s["tasks"])


def test_recycle_candidates_schedule_slots():
    inputs = {
        "dna": {"post_frequency_per_day": 2.0, "avg_er": 5.0, "best_post_hour": 12,
                "category": "tech", "top_topics": ["AI"]},
        "analytics_daily": {"subscriber_delta_pct": 1, "subscriber_delta": 50, "churn_signal": False},
        "recycle_candidates": [
            {"text_preview": "Top AI tools", "text": "Top AI tools for startups", "er": 8.5},
        ],
        "competitors": [],
    }
    s = compute_strategy(inputs, strategy_type="weekly", period_start="2026-06-24", period_end="2026-06-30")
    assert any(t.get("kind") == "recycle" for t in s["tasks"])


@pytest.mark.asyncio
async def test_daily_strategy_does_not_archive_weekly():
    from tools.strategy import archive_old_strategy, save_strategy

    channel = await get_or_create_channel("strat_type_isolation")
    cid = channel["id"]
    try:
        await save_strategy(cid, {
            "strategy_type": "weekly",
            "period_start": "2026-06-25", "period_end": "2026-07-01",
            "goal": "weekly", "post_frequency_per_day": 2,
            "content_mix": [{"format": "text", "pct": 100}],
            "primary_topics": ["x"],
            "tasks": [{"scheduled_date": "2026-06-25", "scheduled_time": "10:00", "format": "text", "topic": "x"}],
        })
        await archive_old_strategy(cid, strategy_type="daily")
        async with AsyncSessionLocal() as session:
            active = (await session.execute(
                select(Strategy).where(Strategy.channel_id == uuid.UUID(cid), Strategy.status == StrategyStatus.active)
            )).scalars().all()
            assert len(active) == 1
            assert active[0].strategy_type.value == "weekly"
    finally:
        async with AsyncSessionLocal() as session:
            ch = (await session.execute(select(Channel).where(Channel.id == uuid.UUID(cid)))).scalar_one()
            await session.delete(ch)
            await session.commit()


def test_growth_tactics_rules():
    # low ER + churn + decline + competitor ahead
    comps = [{"username": "rival", "avg_er": 9.0}]
    tactics = build_growth_tactics(
        avg_er=2.0, churn_signal=True, subscriber_delta=-50, competitors=comps, my_avg_er=2.0
    )
    kinds = {t["tactic"] for t in tactics}
    assert {"increase_polls", "strategy_reset", "reduce_frequency", "mirror_format"} <= kinds


def test_compute_strategy_shape():
    inputs = {
        "dna": {"post_frequency_per_day": 2.0, "avg_er": 5.0, "best_post_hour": 18,
                "top_content_formats": [{"format": "article", "share": 0.6}, {"format": "poll", "share": 0.4}],
                "category": "tech", "sub_category": "ai"},
        "analytics_daily": {"subscriber_delta_pct": 7, "subscriber_delta": 100, "churn_signal": False},
        "competitors": [{"username": "rivalA", "avg_er": 6.0, "top_themes": ["startups"]}],
    }
    s = compute_strategy(inputs, strategy_type="weekly", period_start="2026-06-24", period_end="2026-06-30")
    assert s["post_frequency_per_day"] == 2.5
    slots_per_day = max(1, round(2.5))
    assert len(s["tasks"]) == slots_per_day * 7   # 7 days
    assert "startups" in s["primary_topics"]      # competitor gap topic pulled in
    assert sum(m["pct"] for m in s["content_mix"]) == 100


@pytest.mark.asyncio
async def test_full_strategy_agent_run():
    from agents.strategy import StrategyAgent

    channel = await get_or_create_channel("strategy_test_channel", category="tech")
    cid = channel["id"]
    try:
        # seed a DNA row so load_strategy_inputs has data
        from tools.channel_dna import save_channel_dna
        await save_channel_dna(cid, {
            "subscriber_count": 12000, "avg_er": 4.0, "post_frequency_per_day": 2.0,
            "best_post_hour": 18, "category": "tech", "sub_category": "ai",
            "top_content_formats": [{"format": "article", "share": 0.6}, {"format": "poll", "share": 0.4}],
        })
        result = await StrategyAgent(strategy_type="weekly").run(cid)
        assert result["total_slots"] > 0
        assert result["cron_jobs_created"] >= 1

        async with AsyncSessionLocal() as session:
            strategies = (await session.execute(select(Strategy).where(Strategy.channel_id == cid))).scalars().all()
            assert len(strategies) == 1
            tasks = (await session.execute(select(StrategyTask).where(StrategyTask.channel_id == cid))).scalars().all()
            assert len(tasks) == result["total_slots"]
            crons = (await session.execute(select(CronJob).where(CronJob.channel_id == cid))).scalars().all()
            assert len(crons) == result["cron_jobs_created"]

        active = await get_active_strategy(cid)
        assert active is not None
    finally:
        async with AsyncSessionLocal() as session:
            ch = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
            await session.delete(ch)
            await session.commit()
