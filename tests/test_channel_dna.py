"""Phase 2 — Channel DNA computation + persistence tests (no Telegram needed)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, ChannelDNA
from tools.channel_dna import (
    compute_channel_dna,
    detect_tier,
    extract_top_topics,
    get_channel_category,
    save_channel_dna,
)
from tools.channels import get_or_create_channel

NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def _post(day, hour, fmt, views, reactions, forwards, replies, text=""):
    return {
        "text": text,
        "format": fmt,
        "views": views,
        "forwards": forwards,
        "reactions": reactions,
        "replies": replies,
        "posted_at": datetime(2026, 6, day, hour, 0, tzinfo=timezone.utc),
    }


def _sample_posts():
    edu = "learn how why guide tutorial tips lesson"
    posts = []
    # 3 posts @18:00 high engagement (ER=20)
    for d in (16, 17, 18):
        posts.append(_post(d, 18, "text", 100, 15, 3, 2, edu))
    # 3 posts @09:00 low engagement (ER=2)
    for d in (19, 20, 21):
        posts.append(_post(d, 9, "text", 100, 1, 1, 0, edu))
    # 2 posts @12:00 medium (ER=10) — excluded from best-hour (<3 posts)
    posts.append(_post(22, 12, "poll", 100, 6, 2, 2, edu))
    posts.append(_post(22, 12, "photo", 100, 6, 2, 2, edu))
    return posts


def test_detect_tier():
    assert detect_tier(100) == "new"
    assert detect_tier(10_000) == "mid"
    assert detect_tier(100_000) == "established"
    assert detect_tier(None) == "new"


def test_get_channel_category():
    posts = [{"text": "bitcoin ethereum crypto blockchain defi"}]
    cat, _ = get_channel_category(posts)
    assert cat == "crypto"
    assert get_channel_category([{"text": "random words"}])[0] is None


def test_extract_top_topics():
    posts = [
        {"text": "Amazon deals on electronics today"},
        {"text": "Amazon deals dropping fast on phones"},
        {"text": "Fashion coupons for myntra shoppers"},
        {"text": "Amazon deals electronics again"},
    ]
    topics = extract_top_topics(posts, category="deals", sub_category="shopping")
    # "amazon deals" recurs -> should surface as a specific bigram topic
    assert any("amazon" in t for t in topics)
    # the broad category word itself is excluded
    assert "deals" not in topics


def test_compute_channel_dna_full():
    dna = compute_channel_dna(
        posts=_sample_posts(), member_count=5000, username="@x", now=NOW
    )
    assert dna["insufficient_data"] is False
    assert dna["subscriber_count"] == 5000
    # avg ER = (3*20 + 3*2 + 2*10) / 8 = 10.75
    assert dna["avg_er"] == pytest.approx(10.75, abs=0.01)
    # hour 18 wins (only 18 and 9 have >=3 posts; 18 ER=20 > 9 ER=2)
    assert dna["best_post_hour"] == 18
    # text is the most common format (6 of 8)
    assert dna["top_content_formats"][0]["format"] == "text"
    assert dna["avg_views_per_post"] == 100.0
    assert dna["post_frequency_per_day"] > 0
    assert isinstance(dna["best_post_days"], list) and len(dna["best_post_days"]) <= 3
    # tone fingerprint normalised; educational dominates
    tone = dna["tone_fingerprint"]
    assert abs(sum(tone.values()) - 1.0) < 0.01
    assert max(tone, key=tone.get) == "educational"


def test_compute_channel_dna_insufficient():
    posts = _sample_posts()[:3]  # below MIN_POSTS_FOR_DNA (5)
    dna = compute_channel_dna(posts=posts, member_count=1000, now=NOW)
    assert dna["insufficient_data"] is True
    assert dna["avg_er"] is None


@pytest.mark.asyncio
async def test_save_channel_dna_upsert():
    channel = await get_or_create_channel("dna_test_channel")
    cid = channel["id"]
    try:
        dna = compute_channel_dna(posts=_sample_posts(), member_count=5000, now=NOW)
        r1 = await save_channel_dna(cid, dna)
        assert r1["success"]
        # upsert: second save updates the same row, not a duplicate
        dna2 = dict(dna)
        dna2["avg_er"] = 99.0
        r2 = await save_channel_dna(cid, dna2)
        assert r2["record_id"] == r1["record_id"]

        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(ChannelDNA).where(ChannelDNA.channel_id == cid)
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].avg_er == 99.0
    finally:
        # cleanup channel + dna (cascade)
        async with AsyncSessionLocal() as session:
            ch = (
                await session.execute(select(Channel).where(Channel.id == cid))
            ).scalar_one()
            await session.delete(ch)
            await session.commit()
