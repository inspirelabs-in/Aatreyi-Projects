"""Phase 10 — edge-case hardening tests (roadmap §10)."""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, ChannelDNA, ContentSource, SourceType, StrategyTask, TaskStatus
from tools.channels import get_or_create_channel


class _Dummy:
    pass


# 1. Channel with 0 posts -> DNA marks insufficient_data, doesn't crash
@pytest.mark.asyncio
async def test_dna_zero_posts_insufficient(monkeypatch):
    import agents.channel_dna as dna_mod
    from agents.channel_dna import ChannelDNAAgent

    async def info(c, u):
        return {"channel_id": 1, "title": "T", "member_count": 8000, "has_disappearing_messages": False}
    async def posts(c, ch, days=90, limit=500):
        return {"posts": [], "total_fetched": 0}
    monkeypatch.setattr(dna_mod, "get_telegram_channel_info", info)
    monkeypatch.setattr(dna_mod, "get_channel_posts", posts)

    channel = await get_or_create_channel("edge_zero_posts")
    cid = channel["id"]
    try:
        result = await ChannelDNAAgent("manual").run(cid, username="edge_zero_posts", client=_Dummy())
        assert result["insufficient_data"] is True
        async with AsyncSessionLocal() as s:
            import uuid
            dna = (await s.execute(select(ChannelDNA).where(ChannelDNA.channel_id == uuid.UUID(cid)))).scalar_one()
            assert dna.insufficient_data is True
    finally:
        await _cleanup(cid)


# 2. No content item passes scoring -> original-post fallback
@pytest.mark.asyncio
async def test_content_all_fail_uses_original(monkeypatch):
    import agents.content_intelligence as content_mod
    import tools.content as content_tools
    from agents.content_intelligence import ContentIntelligenceAgent
    from tools.strategy import save_strategy

    channel = await get_or_create_channel("edge_allfail", category="deals")
    cid = channel["id"]

    def rss(url, topic=None, max_age_hours=48):
        # brand-unsafe item -> brand_safety=0 -> auto-fail
        return {"items": [{"title": "casino gambling guaranteed profit", "body_text": "spam",
                           "external_url": "http://x/1", "published_at": datetime.now(timezone.utc),
                           "topics": [], "format_tag": "article"}]}
    monkeypatch.setattr(content_mod, "fetch_rss_feed", rss)

    async def chat(system, user, **kw):
        return '{"post_text":"🛍️ original deals post","cta":"go","hashtags":["deals"]}'
    monkeypatch.setattr(content_tools, "chat_complete", chat)

    try:
        await save_strategy(cid, {
            "strategy_type": "weekly", "period_start": date.today().isoformat(), "period_end": date.today().isoformat(),
            "goal": "g", "post_frequency_per_day": 1, "content_mix": [{"format": "text", "pct": 100}],
            "primary_topics": ["deals"],
            "tasks": [{"scheduled_date": date.today().isoformat(), "scheduled_time": "18:00", "format": "text", "topic": "deals"}],
        })
        import uuid
        async with AsyncSessionLocal() as s:
            task = (await s.execute(select(StrategyTask).where(StrategyTask.channel_id == uuid.UUID(cid)))).scalars().first()
            s.add(ContentSource(channel_id=uuid.UUID(cid), type=SourceType.rss, url="http://x/feed", name="f", is_active=True))
            await s.commit()
        result = await ContentIntelligenceAgent().run(cid, task_id=str(task.id), client=None)
        assert result["used_original"] is True
        assert result["items_passing"] == 0
    finally:
        await _cleanup(cid)


# 3. publish_post with no BOT_TOKEN -> graceful, never raises (forced offline)
@pytest.mark.asyncio
async def test_publish_without_token(monkeypatch):
    from tools import content as content_tools
    monkeypatch.setattr(content_tools.settings, "BOT_TOKEN", None)
    res = await content_tools.publish_post("@somechannel", "hello", post_format="text")
    assert res["published"] is False and "BOT_TOKEN" in res["error"]


# 3a. With a token but no channel access -> graceful error, never raises.
# (Bot must be a channel admin to actually publish; this proves the failure
# is surfaced as an error dict, not a 500.) Fully offline — telegram.Bot stubbed.
@pytest.mark.asyncio
async def test_publish_send_failure_is_graceful(monkeypatch):
    from tools import content as content_tools
    monkeypatch.setattr(content_tools.settings, "BOT_TOKEN", "123:abc")

    class _StubBot:
        def __init__(self, *a, **k): ...
        async def send_message(self, *a, **k):
            raise RuntimeError("Forbidden: bot is not a member of the channel chat")

    import telegram
    monkeypatch.setattr(telegram, "Bot", _StubBot)
    res = await content_tools.publish_post("@somechannel", "hi", post_format="text")
    assert res["published"] is False and "Forbidden" in res["error"]


# 3b. Approving publishes (when the bot can send) and marks the queue row sent
@pytest.mark.asyncio
async def test_publish_generated_post_marks_queue_sent(monkeypatch):
    import uuid
    import tools.content as content_tools
    from db.models import GeneratedPost, PostFormat, PostQueue, QueueStatus

    channel = await get_or_create_channel("edge_publish")
    cid = channel["id"]
    try:
        async with AsyncSessionLocal() as s:
            gp = GeneratedPost(channel_id=uuid.UUID(cid), post_text="ship it",
                               post_format=PostFormat.text)
            s.add(gp)
            await s.flush()
            s.add(PostQueue(channel_id=uuid.UUID(cid), generated_post_id=gp.id))
            await s.commit()
            pid = gp.id

        async def fake_publish(*a, **k):
            return {"published": True, "telegram_message_id": 4242}
        monkeypatch.setattr(content_tools, "publish_post", fake_publish)

        res = await content_tools.publish_generated_post(pid, "@edge_publish")
        assert res["published"] is True and res["telegram_message_id"] == 4242

        async with AsyncSessionLocal() as s:
            pq = (await s.execute(select(PostQueue).where(PostQueue.generated_post_id == pid))).scalar_one()
            assert pq.status == QueueStatus.sent
            assert pq.telegram_message_id == 4242
            assert pq.published_at is not None
    finally:
        await _cleanup(cid)


# 4. Already-processed slot is not re-dispatched (get_due_tasks ignores non-pending)
@pytest.mark.asyncio
async def test_due_tasks_skip_already_generated(monkeypatch):
    from tools.strategy import LOCAL_TZ, get_due_tasks, mark_task_generated, save_strategy
    from datetime import timedelta

    channel = await get_or_create_channel("edge_processed")
    cid = channel["id"]
    now = datetime.now(LOCAL_TZ)
    today = now.date().isoformat()
    soon = (now + timedelta(minutes=10)).strftime("%H:%M")
    try:
        await save_strategy(cid, {
            "strategy_type": "daily", "period_start": today, "period_end": today,
            "goal": "g", "post_frequency_per_day": 1, "content_mix": [{"format": "text", "pct": 100}],
            "primary_topics": ["x"],
            "tasks": [{"scheduled_date": today, "scheduled_time": soon, "format": "text", "topic": "x"}],
        })
        import uuid
        async with AsyncSessionLocal() as s:
            task = (await s.execute(select(StrategyTask).where(StrategyTask.channel_id == uuid.UUID(cid)))).scalars().first()
        # before: due. after marking generated: not due.
        assert any(d["id"] == str(task.id) for d in await get_due_tasks(30))
        await mark_task_generated(str(task.id))
        assert not any(d["id"] == str(task.id) for d in await get_due_tasks(30))
    finally:
        await _cleanup(cid)


# 5. LLM rate-limit (429) -> exponential backoff retries, then succeeds
@pytest.mark.asyncio
async def test_llm_backoff_on_429(monkeypatch):
    import tools.llm as llm

    class _Resp:
        def __init__(self, status): self.status_code = status
        def raise_for_status(self):
            if self.status_code >= 400: raise RuntimeError("http error")
        def json(self): return {"choices": [{"message": {"content": "ok"}}]}

    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            calls["n"] += 1
            return _Resp(429) if calls["n"] == 1 else _Resp(200)

    async def _nosleep(_): return None
    monkeypatch.setattr(llm.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(llm.asyncio, "sleep", _nosleep)
    monkeypatch.setattr(llm.settings, "GROQ_API_KEY", "test-key")

    out = await llm.chat_complete("sys", "user", max_retries=3)
    assert out == "ok"
    assert calls["n"] == 2  # first 429, retried, second 200


async def _cleanup(cid):
    import uuid
    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == uuid.UUID(cid)))).scalar_one()
        await s.delete(ch)
        await s.commit()
