"""Phase 3 — Competitor Intelligence pure-logic + persistence tests."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, Competitor
from tools.channels import get_or_create_channel
from tools.competitor import (
    _parse_brand_list,
    channel_keyword_set,
    competitor_post_er,
    compute_benchmarks,
    compute_competitor_metrics,
    dedup_competitor_list,
    extract_telegram_usernames,
    qualifies_as_competitor,
    rank_competitors,
    save_competitors,
)


def test_qualifies_as_competitor_benchmarks():
    active = {"avg_er": 2.0, "post_frequency_per_day": 1.5}
    # too small (absolute floor)
    ok, why = qualifies_as_competitor(members=200, post_count=10, metrics=active, my_subscribers=0)
    assert not ok and "too small" in why
    # not a peer: 2k subs vs our 100k -> floor 10k
    ok, why = qualifies_as_competitor(members=2000, post_count=10, metrics=active, my_subscribers=100000)
    assert not ok and "peer" in why
    # inactive: no recent posts
    ok, why = qualifies_as_competitor(members=20000, post_count=0,
                                      metrics={"avg_er": None, "post_frequency_per_day": None}, my_subscribers=100000)
    assert not ok and "inactive" in why
    # qualified: established, comparable, active
    ok, why = qualifies_as_competitor(members=20000, post_count=10, metrics=active, my_subscribers=100000)
    assert ok and why == "qualified"


def test_extract_usernames():
    text = (
        "Check https://t.me/techbulletin and @ai_daily plus "
        "telegram.me/startup_india — but t.me/joinchat/XXXX is not a channel."
    )
    out = extract_telegram_usernames(text)
    assert "techbulletin" in out
    assert "ai_daily" in out
    assert "startup_india" in out
    assert "joinchat" not in out  # blocklisted


def test_dedup_drops_managed_existing_and_dupes():
    cands = [
        {"username": "@me"},          # managed
        {"username": "rivalA"},
        {"username": "RivalA"},       # dup (case-insensitive)
        {"username": "tracked1"},     # already tracked
        {"username": "rivalB"},
    ]
    out = dedup_competitor_list(cands, existing_usernames={"tracked1"}, managed_username="@me")
    names = [c["username"] for c in out]
    assert names == ["rivalA", "rivalB"]


def test_competitor_post_er_and_metrics():
    # ER = (reactions + forwards) / max(views,1) * 100
    assert competitor_post_er({"views": 200, "reactions": 10, "forwards": 10}) == pytest.approx(10.0)
    posts = [
        {"views": 100, "reactions": 5, "forwards": 5, "text": "ai startup news",
         "posted_at": datetime(2026, 6, 20, tzinfo=timezone.utc)},
        {"views": 100, "reactions": 15, "forwards": 5, "text": "crypto bitcoin",
         "posted_at": datetime(2026, 6, 22, tzinfo=timezone.utc)},
    ]
    m = compute_competitor_metrics(posts, member_count=5000)
    assert m["avg_er"] == pytest.approx((10.0 + 20.0) / 2)
    assert m["post_frequency_per_day"] is not None
    assert isinstance(m["top_themes"], list)


def test_rank_orders_and_assigns_rank():
    keywords = {"tech", "ai"}
    cands = [
        {"username": "big", "subscriber_count": 50000, "avg_er": 8.0,
         "post_frequency_per_day": 3.0, "top_themes": ["tech", "ai"]},
        {"username": "small", "subscriber_count": 500, "avg_er": 1.0,
         "post_frequency_per_day": 0.5, "top_themes": ["sports"]},
    ]
    ranked = rank_competitors(cands, keywords)
    assert ranked[0]["username"] == "big"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"]
    assert 0 <= ranked[1]["rank_score"] <= 100


def test_disappearing_message_penalty():
    keywords = {"tech"}
    base = dict(subscriber_count=10000, avg_er=5.0, post_frequency_per_day=2.0, top_themes=["tech"])
    a = {"username": "clean", **base}
    b = {"username": "vanish", **base, "has_disappearing_messages": True}
    ranked = rank_competitors([a, b], keywords)
    by = {c["username"]: c["rank_score"] for c in ranked}
    # identical metrics, but the disappearing-message channel is penalised x0.7
    assert by["vanish"] == pytest.approx(by["clean"] * 0.7, abs=0.5)
    assert ranked[0]["username"] == "clean"


def test_channel_keyword_set():
    kw = channel_keyword_set("Tech", "AI", ["Startups", "SaaS"])
    assert kw == {"tech", "ai", "startups", "saas"}


def test_parse_brand_list():
    assert _parse_brand_list('["CashKaro", "CouponDunia", "Zingoy"]') == ["CashKaro", "CouponDunia", "Zingoy"]
    fenced = '```json\n["BrandA","BrandB"]\n```'
    assert _parse_brand_list(fenced) == ["BrandA", "BrandB"]
    # bullet fallback
    out = _parse_brand_list("1. Foo\n2. Bar\n- Baz")
    assert "Foo" in out and "Bar" in out and "Baz" in out


def test_compute_benchmarks():
    comps = [
        {"username": "a", "subscriber_count": 20000, "avg_er": 6.0, "post_frequency_per_day": 3.0,
         "top_themes": ["deals", "fashion"], "rank_score": 90},
        {"username": "b", "subscriber_count": 10000, "avg_er": 4.0, "post_frequency_per_day": 1.0,
         "top_themes": ["electronics"], "rank_score": 70},
    ]
    b = compute_benchmarks(comps, {"avg_er": 0.5})
    assert b["competitor_count"] == 2
    assert b["competitor_avg_er"] == pytest.approx(5.0)
    assert b["competitor_avg_subscribers"] == pytest.approx(15000)
    assert b["er_gap"] == pytest.approx(4.5)        # 5.0 - 0.5
    assert b["top_competitor"] == "a"               # highest rank_score
    assert set(b["competitor_themes"]) == {"deals", "fashion", "electronics"}


@pytest.mark.asyncio
async def test_save_competitors_upsert_and_posts():
    channel = await get_or_create_channel("comp_test_channel")
    cid = channel["id"]
    try:
        comps = [{
            "username": "rivalX", "source": "duckduckgo", "subscriber_count": 12000,
            "avg_er": 4.2, "post_frequency_per_day": 2.0, "top_themes": ["tech"],
            "rank": 1, "rank_score": 88.5, "competitor_tg_id": 999,
            "posts": [{"message_id": 1, "text": "hello world", "format": "text",
                       "views": 100, "forwards": 3, "reactions": 7, "er": 10.0,
                       "posted_at": datetime(2026, 6, 22, tzinfo=timezone.utc)}],
        }]
        r1 = await save_competitors(cid, comps)
        assert r1["upserted"] == 1

        # re-save updates the same competitor (no duplicate row) + replaces posts
        comps[0]["rank_score"] = 77.0
        r2 = await save_competitors(cid, comps)
        assert r2["upserted"] == 1

        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(select(Competitor).where(Competitor.channel_id == cid))
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].rank_score == 77.0
    finally:
        async with AsyncSessionLocal() as session:
            ch = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
            await session.delete(ch)
            await session.commit()
