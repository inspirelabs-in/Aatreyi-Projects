"""Phase 6 — Content Intelligence: 7-signal scorer, EMA, parsing, full agent run."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, ContentSource, GeneratedPost, PostQueue, SourceType
from tools.channels import get_or_create_channel
from tools.content import (
    score_content_item,
    score_content_items,
    update_source_quality,
)
from tools.content import generate_original_post, generate_post
from tools.llm import parse_poll_json, parse_post_json

NOW = datetime.now(timezone.utc)


def _ctx(**over):
    base = {
        "score_threshold": 4,
        "strategy": {"primary_topics": ["ai", "startups"]},
        "recent_post_fingerprints": [],
        "competitor_post_fingerprints": [],
    }
    base.update(over)
    return base


def test_scorer_all_green():
    item = {
        "title": "10 tools every AI startup should use",
        "body_text": "ai startups productivity tools",
        "published_at": NOW - timedelta(hours=2),
        "topics": ["ai", "startups"],
    }
    s = score_content_item(item, _ctx())
    assert s["relevance"] == 1
    assert s["freshness"] == 1
    assert s["novelty"] == 1
    assert s["goal_alignment"] == 1
    assert s["virality"] == 1           # "10 ... tools" hook
    assert s["competitor_set"] == 1
    assert s["brand_safety"] == 1
    assert s["total"] == 7 and s["passed"] is True


def test_brand_safety_autofails():
    item = {"title": "guaranteed profit casino", "body_text": "ai startups",
            "topics": ["ai", "startups"], "published_at": NOW}
    s = score_content_item(item, _ctx())
    assert s["brand_safety"] == 0
    assert s["passed"] is False  # auto-fail regardless of total


def test_freshness_decays():
    old = {"title": "ai news", "body_text": "ai", "topics": ["ai"],
           "published_at": NOW - timedelta(hours=72)}
    assert score_content_item(old, _ctx())["freshness"] == 0
    ever = score_content_item(old, _ctx(evergreen=True))  # 168h window
    assert ever["freshness"] == 1


def test_novelty_and_competitor_set():
    item = {"title": "AI tools roundup for startups", "body_text": "ai startups tools",
            "topics": ["ai"], "published_at": NOW}
    dup = _ctx(recent_post_fingerprints=["AI tools roundup for startups today"])
    assert score_content_item(item, dup)["novelty"] == 0
    comp = _ctx(competitor_post_fingerprints=["AI tools roundup for startups now"])
    assert score_content_item(item, comp)["competitor_set"] == 0


def test_virality_engagement_case():
    item = {"title": "no hook here", "body_text": "ai", "topics": ["ai"], "published_at": NOW,
            "views": 1000, "forwards": 30, "reactions": 10}  # 4% > 2%
    assert score_content_item(item, _ctx())["virality"] == 1


def test_score_items_aggregate():
    items = [
        {"title": "10 ai tools", "body_text": "ai startups", "topics": ["ai", "startups"], "published_at": NOW},
        {"title": "casino gambling", "body_text": "spam", "topics": [], "published_at": NOW},
    ]
    r = score_content_items(items, _ctx())
    assert r["passing_count"] == 1


def test_source_quality_ema_and_deactivate():
    avg, total = update_source_quality(0.0, 0, 6)
    assert avg == 6.0 and total == 1
    # below 2.5 after 20 items -> agent deactivates (logic tested in tool path)
    avg2, total2 = update_source_quality(2.0, 19, 1)
    assert total2 == 20 and avg2 < 2.5


def test_parse_post_json_variants():
    fenced = '```json\n{"post_text":"hi","cta":"click","hashtags":["ai"]}\n```'
    out = parse_post_json(fenced)
    assert out["post_text"] == "hi" and out["cta"] == "click" and out["hashtags"] == ["#ai"]
    plain = parse_post_json("just text, no json")
    assert plain["post_text"] == "just text, no json"


def test_parse_poll_json():
    out = parse_poll_json('```json\n{"question":"Which LLM?","options":["GPT","Claude","Llama"],"hashtags":["ai"]}\n```')
    assert out["question"] == "Which LLM?"
    assert out["options"] == ["GPT", "Claude", "Llama"]
    # fallback: lines
    fb = parse_poll_json("Best editor?\n- VSCode\n- Vim\n- Emacs")
    assert fb["question"] == "Best editor?" and len(fb["options"]) >= 2


@pytest.mark.asyncio
async def test_generate_poll(monkeypatch):
    import tools.content as content

    async def fake_chat(system, user, **kw):
        assert "poll" in system.lower()
        return '{"question":"🤔 Which AI tool?","options":["ChatGPT","Claude"],"hashtags":["ai"]}'
    monkeypatch.setattr(content, "chat_complete", fake_chat)

    out = await generate_post({"title": "ai tools"}, {"topic": "ai", "format": "poll"}, {})
    assert out["format"] == "poll"
    assert out["poll_options"] == ["ChatGPT", "Claude"]
    assert "Which AI tool" in out["post_text"]


@pytest.mark.asyncio
async def test_generate_photo_uses_source_image(monkeypatch):
    import tools.content as content

    async def fake_chat(system, user, **kw):
        return '{"post_text":"📸 caption here","cta":"see more","hashtags":["x"]}'
    monkeypatch.setattr(content, "chat_complete", fake_chat)

    item = {"title": "t", "body_text": "b", "image_url": "http://img/x.jpg"}
    out = await generate_post(item, {"topic": "ai", "format": "photo"}, {})
    assert out["format"] == "photo"
    assert out["media_url"] == "http://img/x.jpg"


@pytest.mark.asyncio
async def test_generate_photo_uses_topic_image_without_source(monkeypatch):
    import tools.content as content

    async def fake_chat(system, user, **kw):
        return '{"post_text":"text body","cta":"","hashtags":[]}'
    monkeypatch.setattr(content, "chat_complete", fake_chat)

    # original post (no source) requesting photo -> attach a topic image so it
    # stays a real photo post (honours the strategy's format mix, no text downgrade)
    out = await generate_original_post({"topic": "ai", "format": "photo"}, {})
    assert out["format"] == "photo"
    assert out["media_url"] and out["media_url"].startswith("http")


@pytest.mark.asyncio
async def test_generate_link_embeds_url(monkeypatch):
    import tools.content as content

    async def fake_chat(system, user, **kw):
        return '{"post_text":"check this out","cta":"read","hashtags":[]}'
    monkeypatch.setattr(content, "chat_complete", fake_chat)

    item = {"title": "t", "body_text": "b", "external_url": "http://news/article"}
    out = await generate_post(item, {"topic": "ai", "format": "link"}, {})
    assert out["format"] == "link"
    # One-link design: the URL is carried ONLY by the clickable button (link_url),
    # never inlined in the body (which would double-link the post).
    assert out["link_url"] == "http://news/article"
    assert "http://news/article" not in (out["post_text"] or "")


@pytest.mark.asyncio
async def test_full_content_agent_run(monkeypatch):
    """End-to-end with RSS fetch + LLM mocked: scoring -> generate -> queue."""
    import agents.content_intelligence as ci
    import tools.content as content

    channel = await get_or_create_channel("content_test_channel", category="tech")
    cid = channel["id"]

    # seed: active strategy + a task + an RSS source
    from tools.strategy import save_strategy
    saved = await save_strategy(cid, {
        "strategy_type": "weekly", "period_start": "2026-06-24", "period_end": "2026-06-30",
        "goal": "grow", "post_frequency_per_day": 1, "content_mix": [{"format": "text", "pct": 100}],
        "primary_topics": ["ai", "startups"],
        "tasks": [{"scheduled_date": "2026-06-24", "scheduled_time": "18:00", "format": "text", "topic": "ai"}],
    })
    async with AsyncSessionLocal() as session:
        session.add(ContentSource(channel_id=__import__("uuid").UUID(cid), type=SourceType.rss,
                                  url="http://example.com/feed", name="feed", is_active=True))
        await session.commit()

    # find the task id
    from db.models import StrategyTask
    async with AsyncSessionLocal() as session:
        task = (await session.execute(select(StrategyTask).where(StrategyTask.channel_id == __import__("uuid").UUID(cid)))).scalars().first()
    task_id = str(task.id)

    # mock RSS fetch (no network) -> one strong item
    def fake_rss(url, topic=None, max_age_hours=48):
        return {"items": [{
            "title": "10 AI tools every startup needs", "body_text": "ai startups tools",
            "external_url": "http://example.com/a1", "published_at": NOW,
            "topics": ["ai", "startups"], "format_tag": "article",
        }]}
    # agent imports fetch_rss_feed into its own namespace -> patch it there
    monkeypatch.setattr(ci, "fetch_rss_feed", fake_rss)

    # mock LLM (no Groq network)
    async def fake_chat(system, user, **kw):
        return '{"post_text":"🚀 10 AI tools for startups","cta":"Which do you use?","hashtags":["ai"]}'
    monkeypatch.setattr(content, "chat_complete", fake_chat)

    try:
        result = await ci.ContentIntelligenceAgent().run(cid, task_id=task_id)
        assert result["review_status"] == "pending"
        assert result["used_original"] is False
        assert result["items_passing"] >= 1

        async with AsyncSessionLocal() as session:
            gp = (await session.execute(select(GeneratedPost).where(GeneratedPost.channel_id == __import__("uuid").UUID(cid)))).scalars().all()
            assert len(gp) == 1 and "AI tools" in gp[0].post_text
            pq = (await session.execute(select(PostQueue).where(PostQueue.channel_id == __import__("uuid").UUID(cid)))).scalars().all()
            assert len(pq) == 1
    finally:
        async with AsyncSessionLocal() as session:
            ch = (await session.execute(select(Channel).where(Channel.id == __import__("uuid").UUID(cid)))).scalar_one()
            await session.delete(ch)
            await session.commit()
