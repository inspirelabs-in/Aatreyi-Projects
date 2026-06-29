"""Phase 10 — end-to-end pipeline test.

Runs the real agent code for the full Tier-B/C chain
(DNA -> Competitor -> Analytics -> Strategy -> Content -> review queue) against
the real tga DB, stubbing only the external boundaries: Telegram (Telethon),
competitor discovery (web/search), and the LLM (Groq).
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import (
    AnalyticsSnapshot, Channel, ChannelDNA, ContentSource, GeneratedPost,
    PostQueue, SourceType, Strategy, StrategyStatus, StrategyTask,
)
from tools.channels import get_or_create_channel

NOW = datetime.now(timezone.utc)


class _DummyClient:
    pass


def _synthetic_posts(n=24):
    posts = []
    for i in range(n):
        posts.append({
            "message_id": i,
            "text": f"Big AI startup deal {i} — how to save on tools",
            "format": "photo" if i % 2 else "text",
            "views": 1000,
            "forwards": 30,
            "reactions": 40,
            "replies": 5,
            "posted_at": NOW - timedelta(days=i % 10, hours=i % 5),
        })
    return posts


async def _fake_info(client, username):
    return {"channel_id": 555, "title": "E2E Channel", "description": "",
            "username": username, "member_count": 20000, "has_disappearing_messages": False}


async def _fake_posts(client, channel, days=90, limit=500):
    return {"posts": _synthetic_posts(), "total_fetched": 24}


@pytest.mark.asyncio
async def test_full_pipeline_e2e(monkeypatch):
    import agents.channel_dna as dna_mod
    import agents.analytics as an_mod
    import agents.competitor_intelligence as comp_mod
    import agents.content_intelligence as content_mod
    import tools.content as content_tools

    from agents.analytics import AnalyticsAgent
    from agents.channel_dna import ChannelDNAAgent
    from agents.competitor_intelligence import CompetitorIntelligenceAgent
    from agents.content_intelligence import ContentIntelligenceAgent
    from agents.strategy import StrategyAgent

    # ── stub Telegram boundary in each agent that uses it ────────────────────
    for mod in (dna_mod, an_mod):
        monkeypatch.setattr(mod, "get_telegram_channel_info", _fake_info)
        monkeypatch.setattr(mod, "get_channel_posts", _fake_posts)
    monkeypatch.setattr(comp_mod, "get_telegram_channel_info", _fake_info)

    # ── stub competitor discovery (no network/LLM) -> empty market list ──────
    async def _no_brands(*a, **k): return []
    async def _no_tg(*a, **k): return []
    monkeypatch.setattr(comp_mod, "discover_competitor_brands", _no_brands)
    monkeypatch.setattr(comp_mod, "find_brand_telegram_channels", _no_tg)

    # ── stub RSS fetch + LLM for the content agent ───────────────────────────
    def _fake_rss(url, topic=None, max_age_hours=48):
        return {"items": [{
            "title": "10 tools every startup needs to save money",
            "body_text": "ai startups deals tools discounts",
            "external_url": "http://example.com/e2e", "published_at": NOW,
            "topics": ["deals", "ai"], "format_tag": "article", "image_url": None,
        }]}
    monkeypatch.setattr(content_mod, "fetch_rss_feed", _fake_rss)

    async def _fake_chat(system, user, **kw):
        return '{"post_text":"🛍️ Top deals on AI tools today!","cta":"Grab now","hashtags":["deals"]}'
    monkeypatch.setattr(content_tools, "chat_complete", _fake_chat)

    channel = await get_or_create_channel("e2e_pipeline_channel", category="deals")
    cid = channel["id"]
    client = _DummyClient()
    try:
        # 1. DNA  2. Competitor  3. Analytics  4. Strategy
        await ChannelDNAAgent("manual").run(cid, username="e2e_pipeline_channel", client=client)
        await CompetitorIntelligenceAgent("manual").run(cid, client=client)
        await AnalyticsAgent("daily", trigger="manual").run(cid, username="e2e_pipeline_channel", client=client)
        await StrategyAgent("weekly").run(cid)

        # seed an RSS source, then 5. Content on the first task
        import uuid as _uuid
        async with AsyncSessionLocal() as s:
            s.add(ContentSource(channel_id=_uuid.UUID(cid), type=SourceType.rss,
                                url="http://example.com/feed", name="feed", is_active=True))
            await s.commit()
            task = (await s.execute(select(StrategyTask).where(StrategyTask.channel_id == _uuid.UUID(cid)))).scalars().first()

        result = await ContentIntelligenceAgent("post_slot").run(cid, task_id=str(task.id), client=None)

        # ── assert the full chain landed in the DB ───────────────────────────
        async with AsyncSessionLocal() as s:
            c = _uuid.UUID(cid)
            dna = (await s.execute(select(ChannelDNA).where(ChannelDNA.channel_id == c))).scalar_one()
            assert dna.insufficient_data is False and dna.avg_er is not None
            snap = (await s.execute(select(AnalyticsSnapshot).where(AnalyticsSnapshot.channel_id == c))).scalars().all()
            assert len(snap) == 1
            strat = (await s.execute(select(Strategy).where(Strategy.channel_id == c, Strategy.status == StrategyStatus.active))).scalars().first()
            assert strat is not None
            tasks = (await s.execute(select(StrategyTask).where(StrategyTask.channel_id == c))).scalars().all()
            assert len(tasks) > 0
            gp = (await s.execute(select(GeneratedPost).where(GeneratedPost.channel_id == c))).scalars().all()
            assert len(gp) == 1 and "deals" in (gp[0].hashtags or [""])[0].lower() or gp[0].post_text
            pq = (await s.execute(select(PostQueue).where(PostQueue.channel_id == c))).scalars().all()
            assert len(pq) == 1

        assert result["review_status"] == "pending"
    finally:
        async with AsyncSessionLocal() as s:
            import uuid as _uuid
            ch = (await s.execute(select(Channel).where(Channel.id == _uuid.UUID(cid)))).scalar_one()
            await s.delete(ch)
            await s.commit()
