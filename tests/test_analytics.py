"""Phase 4 — Analytics computation + persistence tests (no Telegram needed)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import AnalyticsSnapshot, Channel
from tools.analytics import (
    compute_analytics_snapshot,
    compute_er_by_format,
    detect_sustained_decline,
    flag_strategy_review,
    generate_analytics_digest,
    save_analytics_snapshot,
)
from tools.channels import get_or_create_channel


def test_sustained_decline_detector():
    # 3 periods shrinking in a row (no spike) -> sustained churn
    assert detect_sustained_decline(-0.3, [-0.2, -0.4]) is True
    # a single dip after growth -> not sustained (GrabOn case)
    assert detect_sustained_decline(-0.01, [0.045]) is False
    # growth -> never churn
    assert detect_sustained_decline(0.5, [-0.2, -0.3]) is False


def test_compute_snapshot_flags_sustained_decline():
    # current -0.3% with two prior negative periods -> churn_signal on slow bleed
    snap = compute_analytics_snapshot(
        channel_id="x", current_member_count=9970, posts=[],
        previous_snapshot={"subscriber_count": 10000},
        history=[{"subscriber_delta_pct": -0.2}, {"subscriber_delta_pct": -0.25}],
        snapshot_type="daily",
    )
    assert snap["churn_signal"] is True
    assert snap["churn_type"] == "sustained"


def _post(hour, fmt, views, reactions, forwards, replies):
    return {
        "format": fmt, "views": views, "reactions": reactions,
        "forwards": forwards, "replies": replies,
        "posted_at": datetime(2026, 6, 22, hour, 0, tzinfo=timezone.utc),
    }


def test_subscriber_delta_and_reach():
    posts = [_post(10, "text", 1000, 50, 20, 10)]
    snap = compute_analytics_snapshot(
        channel_id="x", current_member_count=10300, posts=posts,
        previous_snapshot={"subscriber_count": 10000}, snapshot_type="daily",
    )
    assert snap["subscriber_delta"] == 300
    assert snap["subscriber_delta_pct"] == pytest.approx(3.0)
    # reach = views*(1 + forwards/subs*5) = 1000*(1 + 20/10300*5)
    assert snap["reach"] == int(round(1000 * (1 + 20 / 10300 * 5)))


def test_no_posts_nulls():
    snap = compute_analytics_snapshot(
        channel_id="x", current_member_count=5000, posts=[],
        previous_snapshot={"subscriber_count": 5000}, snapshot_type="daily",
    )
    assert snap["total_posts"] == 0
    assert snap["avg_views"] is None
    assert snap["avg_er"] is None


def test_churn_signal_triggers():
    # current drop -4%, rolling avg of prior ~ -0.5% -> 4 > 2*0.5
    history = [{"subscriber_delta_pct": -0.5}, {"subscriber_delta_pct": -0.5},
               {"subscriber_delta_pct": -0.5}, {"subscriber_delta_pct": -0.5}]
    snap = compute_analytics_snapshot(
        channel_id="x", current_member_count=9600, posts=[],
        previous_snapshot={"subscriber_count": 10000}, snapshot_type="daily",
        history=history,
    )
    assert snap["subscriber_delta"] == -400
    assert snap["churn_signal"] is True
    assert any(i["type"] == "churn" for i in snap["insights"])


def test_churn_not_triggered_on_growth():
    snap = compute_analytics_snapshot(
        channel_id="x", current_member_count=10400, posts=[],
        previous_snapshot={"subscriber_count": 10000}, snapshot_type="daily",
        history=[{"subscriber_delta_pct": -0.5}],
    )
    assert snap["churn_signal"] is False


def test_er_drop_and_spike_insights():
    posts = [_post(10, "text", 1000, 5, 3, 2)]  # low ER
    drop = compute_analytics_snapshot(
        channel_id="x", current_member_count=10000, posts=posts,
        previous_snapshot={"subscriber_count": 10000, "avg_er": 50.0}, snapshot_type="daily",
    )
    assert any(i["type"] == "er_drop" for i in drop["insights"])

    posts2 = [_post(10, "text", 1000, 500, 300, 200)]  # high ER
    spike = compute_analytics_snapshot(
        channel_id="x", current_member_count=10000, posts=posts2,
        previous_snapshot={"subscriber_count": 10000, "avg_er": 1.0}, snapshot_type="daily",
    )
    assert any(i["type"] == "er_spike" for i in spike["insights"])


def test_format_winner_insight():
    posts = [
        _post(10, "poll", 1000, 200, 100, 50),   # high ER
        _post(11, "poll", 1000, 200, 100, 50),
        _post(12, "text", 1000, 5, 2, 1),         # low ER
        _post(13, "text", 1000, 5, 2, 1),
    ]
    snap = compute_analytics_snapshot(
        channel_id="x", current_member_count=10000, posts=posts,
        previous_snapshot={"subscriber_count": 10000}, snapshot_type="daily",
    )
    note = next((i["note"] for i in snap["insights"] if i["type"] == "format"), "")
    assert "poll" in note and "text" in note


def test_low_post_volume_insight():
    # target 3/day -> threshold round(3*1*0.6)=2; only 1 post -> below
    snap = compute_analytics_snapshot(
        channel_id="x", current_member_count=10000,
        posts=[_post(10, "text", 1000, 10, 5, 2)],
        previous_snapshot={"subscriber_count": 10000}, snapshot_type="daily",
        target_post_frequency=3.0,
    )
    assert any(i["type"] == "volume" for i in snap["insights"])


def test_er_by_format_and_digest():
    posts = [_post(10, "poll", 1000, 100, 0, 0), _post(11, "text", 1000, 10, 0, 0)]
    er = compute_er_by_format(posts, subscriber_count=10000)
    assert er["poll"] > er["text"]
    text = generate_analytics_digest({
        "snapshot_type": "daily", "subscriber_count": 10000, "subscriber_delta": 100,
        "subscriber_delta_pct": 1.0, "avg_views": 900, "avg_er": 5.0, "total_posts": 3,
        "insights": [{"type": "growth", "note": "Best single-day gain this month"}],
    })
    assert "Best single-day gain" in text


@pytest.mark.asyncio
async def test_save_snapshot_and_flag_review():
    channel = await get_or_create_channel("analytics_test_channel")
    cid = channel["id"]
    try:
        snap = compute_analytics_snapshot(
            channel_id=cid, current_member_count=10000,
            posts=[_post(10, "text", 1000, 10, 5, 2)],
            previous_snapshot={"subscriber_count": 9900}, snapshot_type="daily",
            period_start="2026-06-23", period_end="2026-06-23",
        )
        saved = await save_analytics_snapshot(cid, snap)
        assert saved["success"]

        flagged = await flag_strategy_review(cid, "churn_signal")
        assert flagged["flagged"]

        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(AnalyticsSnapshot).where(AnalyticsSnapshot.channel_id == cid)
                )
            ).scalars().all()
            assert len(rows) == 1
            ch = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
            assert ch.needs_strategy_review is True
            assert ch.strategy_review_reason == "churn_signal"
    finally:
        async with AsyncSessionLocal() as session:
            ch = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
            await session.delete(ch)
            await session.commit()
