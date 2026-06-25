"""Phase 9 — FastAPI backend endpoint tests against the real tga DB."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.main import app
from db.base import AsyncSessionLocal
from db.models import Channel

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_agent_runs_endpoint():
    r = client.get("/api/agent-runs?limit=5")
    assert r.status_code == 200 and isinstance(r.json(), list)
    r2 = client.get("/api/agent-runs?status=failed&limit=5")
    assert r2.status_code == 200


def test_admin_endpoints_require_admin_role():
    # USER (default / no header) is forbidden from admin endpoints
    for path in ("/api/admin/overview", "/api/admin/channels",
                 "/api/admin/agent-performance", "/api/admin/system-health",
                 "/api/admin/global-events"):
        assert client.get(path).status_code == 403, path
        assert client.get(path, headers={"X-Role": "user"}).status_code == 403, path
    # ADMIN role unlocks them
    ov = client.get("/api/admin/overview", headers={"X-Role": "admin"})
    assert ov.status_code == 200
    body = ov.json()
    assert {"channels", "agent_runs", "success_rate", "pending_review"} <= set(body)
    perf = client.get("/api/admin/agent-performance", headers={"X-Role": "admin"}).json()
    assert {p["agent"] for p in perf} == {
        "channel_dna", "competitor_intelligence", "analytics", "strategy", "content_intelligence"}


def test_control_endpoint_shape():
    uname = "api_control_channel"
    _delete_channel_sync(uname)
    cid = client.post("/api/channels", json={"telegram_username": uname, "category": "deals"}).json()["channel_id"]
    try:
        r = client.get(f"/api/channels/{cid}/control")
        assert r.status_code == 200
        body = r.json()
        assert {"channel", "events", "pipeline", "system"} <= set(body)
        assert {p["agent"] for p in body["pipeline"]} == {
            "channel_dna", "competitor_intelligence", "analytics", "strategy", "content_intelligence"}
        assert body["system"]["agent_health"] in ("green", "yellow", "red")
    finally:
        _delete_channel_sync(uname)


def _delete_channel_sync(username: str):
    import asyncio

    async def _del():
        async with AsyncSessionLocal() as s:
            ch = (await s.execute(select(Channel).where(Channel.telegram_username == username))).scalar_one_or_none()
            if ch:
                await s.delete(ch)
                await s.commit()
    asyncio.get_event_loop().run_until_complete(_del()) if False else asyncio.run(_del())


def test_onboard_and_read_endpoints():
    uname = "api_test_channel"
    _delete_channel_sync(uname)
    # onboard
    r = client.post("/api/channels", json={"telegram_username": uname, "category": "deals"})
    assert r.status_code == 201
    cid = r.json()["channel_id"]
    try:
        # list includes it
        assert any(c["id"] == cid for c in client.get("/api/channels").json())

        # seed DNA + analytics + strategy + competitor so read endpoints have data
        _seed(cid)

        dash = client.get(f"/api/channels/{cid}/dashboard").json()
        assert dash["channel"]["telegram_username"] == uname
        assert dash["kpis"]["subscriber_count"] == 12000

        an = client.get(f"/api/channels/{cid}/analytics?snapshot_type=daily").json()
        assert len(an) == 1 and an[0]["subscriber_count"] == 12000

        strat = client.get(f"/api/channels/{cid}/strategy").json()
        assert strat["primary_topics"] == ["deals"]
        assert len(strat["tasks"]) == 1

        comps = client.get(f"/api/channels/{cid}/competitors").json()
        assert comps[0]["competitor_username"] == "rivaldeals"

        # queue + actions
        q = client.get(f"/api/channels/{cid}/queue").json()
        assert len(q) == 1
        pid = q[0]["generated_post_id"]

        edit = client.put(f"/api/channels/{cid}/queue/{pid}", json={"edited_text": "new text"})
        assert edit.status_code == 200 and edit.json()["review_status"] == "edited"

        # 404 on unknown channel
        assert client.get(f"/api/channels/{uuid.uuid4()}/dashboard").status_code == 404
    finally:
        _delete_channel_sync(uname)


def _seed(cid: str):
    import asyncio
    from datetime import date, time

    async def _s():
        from db.models import (AnalyticsSnapshot, ChannelDNA, Competitor, GeneratedPost,
                               SnapshotType, Strategy, StrategyStatus, StrategyTask, StrategyType,
                               PostFormat, ReviewStatus, DiscoverySource)
        c = uuid.UUID(cid)
        async with AsyncSessionLocal() as s:
            s.add(ChannelDNA(channel_id=c, subscriber_count=12000, avg_er=4.0,
                             post_frequency_per_day=2.0, best_post_hour=18, category="deals"))
            s.add(AnalyticsSnapshot(channel_id=c, snapshot_type=SnapshotType.daily,
                                    period_start=date.today(), period_end=date.today(),
                                    subscriber_count=12000, subscriber_delta=100, avg_er=4.0, total_posts=3))
            strat = Strategy(channel_id=c, strategy_type=StrategyType.weekly,
                             period_start=date.today(), period_end=date.today(),
                             goal="grow", post_frequency_per_day=2.0,
                             content_mix=[{"format": "text", "pct": 100}], primary_topics=["deals"],
                             status=StrategyStatus.active)
            s.add(strat)
            await s.flush()
            s.add(StrategyTask(strategy_id=strat.id, channel_id=c, scheduled_date=date.today(),
                               scheduled_time=time(18, 0), format="text", topic="deals"))
            s.add(Competitor(channel_id=c, competitor_username="rivaldeals", subscriber_count=20000,
                             avg_er=5.0, rank=1, rank_score=90.0, source=DiscoverySource.duckduckgo))
            s.add(GeneratedPost(channel_id=c, post_text="🛍️ deal!", post_format=PostFormat.text,
                                review_status=ReviewStatus.pending))
            await s.commit()
    asyncio.run(_s())
