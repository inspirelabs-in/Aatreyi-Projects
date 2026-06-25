"""Content Intelligence tools (Phase 6).

Fetch (RSS/web), the 7-signal scorer (formulae.md §5), source-quality EMA,
LLM generation (Groq), review queue, and publishing. The scorer and EMA are
pure and unit-testable; fetch/generate/publish do I/O.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select

from config import settings
from db.base import AsyncSessionLocal
from db.models import (
    Channel,
    ContentItem,
    ContentItemStatus,
    ContentScore,
    ContentSource,
    GeneratedPost,
    PostQueue,
    QueueStatus,
    ReviewStatus,
    Strategy,
    StrategyStatus,
    StrategyTask,
    CompetitorPost,
    Competitor,
)
from tools.llm import chat_complete, parse_poll_json, parse_post_json

# ── Constants (formulae.md §5) ───────────────────────────────────────────────
FRESHNESS_HOURS = 48
EVERGREEN_HOURS = 168
NOVELTY_SIM = 0.65
COMPETITOR_SIM = 0.60
VIRALITY_ENGAGEMENT = 0.02

HOOK_PATTERNS = [
    r"\d+\s+(ways|tools|tips|reasons|mistakes)",
    r"(how to|why|what happens when)",
    r"(breaking|just in|thread)",
    r"(you (need|must|should)|everyone)",
]
BLOCK_KEYWORDS = [
    "adult", "porn", "xxx", "gambling", "casino", "drugs", "weapon",
    "kill", "bomb", "hack your", "get rich quick", "100% returns",
    "guaranteed profit", "mlm", "pyramid", "click here to earn",
    "free money", "nude", "explicit",
]
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "with", "this", "that", "it", "as", "at", "by", "be", "from", "you", "your",
}


# ── Tokenisation / similarity (pure) ─────────────────────────────────────────
def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── 7-signal scorer (pure; formulae.md §5) ───────────────────────────────────
def _item_topics(item: dict, channel_topics: set[str]) -> set[str]:
    """Item topics from explicit tags, else inferred by matching channel topics."""
    explicit = {str(t).lower() for t in (item.get("topics") or [])}
    if explicit:
        return explicit
    text = f"{item.get('title','')} {item.get('body_text','')}".lower()
    return {t for t in channel_topics if t and t.lower() in text}


def score_content_item(item: dict, context: dict) -> dict[str, int]:
    threshold = context.get("score_threshold", 4)
    strategy = context.get("strategy") or {}
    channel_topics = {str(t).lower() for t in (strategy.get("primary_topics") or [])}
    recent = context.get("recent_post_fingerprints") or []
    competitor = context.get("competitor_post_fingerprints") or []
    evergreen = bool(context.get("evergreen"))

    title = item.get("title") or ""
    body = item.get("body_text") or ""
    item_topics = _item_topics(item, channel_topics)
    item_tokens = _tokens(f"{title} {body[:200]}")

    # 1. Relevance
    relevance = 1 if (channel_topics & item_topics) else 0

    # 2. Freshness
    pub = item.get("published_at")
    if pub is None:
        freshness = 1
    else:
        age_h = (datetime.now(timezone.utc) - _aware(pub)).total_seconds() / 3600
        freshness = 1 if age_h <= (EVERGREEN_HOURS if evergreen else FRESHNESS_HOURS) else 0

    # 3. Novelty (vs recent own posts)
    novelty = 1
    for r in recent:
        if _jaccard(item_tokens, _tokens(r)) > NOVELTY_SIM:
            novelty = 0
            break

    # 4. Goal alignment
    if channel_topics:
        goal_match = len(channel_topics & item_topics) / len(channel_topics)
        goal_alignment = 1 if goal_match >= 0.33 else 0
    else:
        goal_alignment = 0

    # 5. Virality
    views = item.get("views")
    if views:  # Case A: engagement metrics present
        share = (item.get("forwards") or 0) / max(views, 1)
        react = (item.get("reactions") or 0) / max(views, 1)
        virality = 1 if (share * 0.6 + react * 0.4) >= VIRALITY_ENGAGEMENT else 0
    else:  # Case B: hook-pattern proxy
        low = title.lower()
        virality = 1 if any(re.search(p, low) for p in HOOK_PATTERNS) else 0

    # 6. Competitor set
    competitor_set = 1
    for c in competitor:
        if _jaccard(item_tokens, _tokens(c)) > COMPETITOR_SIM:
            competitor_set = 0
            break

    # 7. Brand safety
    text_lower = f"{title} {body[:500]}".lower()
    brand_safety = 0 if any(kw in text_lower for kw in BLOCK_KEYWORDS) else 1

    total = relevance + freshness + novelty + goal_alignment + virality + competitor_set + brand_safety
    passed = bool(total >= threshold and brand_safety == 1)
    return {
        "relevance": relevance, "freshness": freshness, "novelty": novelty,
        "goal_alignment": goal_alignment, "virality": virality,
        "competitor_set": competitor_set, "brand_safety": brand_safety,
        "total": total, "passed": passed, "threshold_used": threshold,
    }


def score_content_items(items: list[dict], context: dict) -> dict[str, Any]:
    scored = [{"content_item": it, "scores": score_content_item(it, context)} for it in items]
    passing = sum(1 for s in scored if s["scores"]["passed"])
    return {"scored_items": scored, "passing_count": passing}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Source quality EMA (pure; formulae.md §5.2) ──────────────────────────────
def update_source_quality(old_avg: float, total_scored: int, item_score: int) -> tuple[float, int]:
    """Running average of total_score; returns (new_avg, new_total)."""
    new_avg = (old_avg * total_scored + item_score) / (total_scored + 1)
    return round(new_avg, 4), total_scored + 1


# ── Fetch: RSS (I/O) ─────────────────────────────────────────────────────────
def fetch_rss_feed(url: str, topic: str | None = None, max_age_hours: int = 48) -> dict[str, Any]:
    import feedparser

    parsed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    items: list[dict] = []
    for e in parsed.entries:
        published = _parse_struct_time(e)
        if published and published < cutoff:
            continue
        title = getattr(e, "title", "") or ""
        body = (getattr(e, "summary", "") or getattr(e, "description", "") or "")[:1000]
        if topic and topic.lower() not in f"{title} {body}".lower():
            continue
        items.append({
            "title": title, "body_text": body,
            "author": getattr(e, "author", None),
            "published_at": published,
            "external_url": getattr(e, "link", None),
            "image_url": _rss_image(e),
            "format_tag": "article",
        })
    return {"items": items}


def _rss_image(entry) -> str | None:
    for mc in getattr(entry, "media_content", []) or []:
        if mc.get("url"):
            return mc["url"]
    for mt in getattr(entry, "media_thumbnail", []) or []:
        if mt.get("url"):
            return mt["url"]
    for enc in getattr(entry, "enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    return None


def _parse_struct_time(entry) -> datetime | None:
    import time as _t

    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if st:
        return datetime.fromtimestamp(_t.mktime(st), tz=timezone.utc)
    return None


async def scrape_website(url: str, topic: str | None = None) -> dict[str, Any]:
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        resp = await c.get(url)
        resp.raise_for_status()
        html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    title = (soup.title.string if soup.title else "") or ""
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    body = "\n".join(p for p in paragraphs if len(p) > 40)[:2000]
    og = soup.find("meta", property="og:image")
    image_url = og.get("content") if og else None
    return {"title": title.strip(), "body_text": body, "author": None,
            "published_at": None, "external_url": url, "image_url": image_url}


async def check_url_used(channel_id: str | uuid.UUID, external_url: str) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(ContentItem).where(
                    ContentItem.channel_id == cid,
                    ContentItem.external_url == external_url,
                    ContentItem.fetched_at >= cutoff,
                )
            )
        ).scalars().first()
    return {"already_used": row is not None}


# ── Context / source loaders ─────────────────────────────────────────────────
async def get_strategy_task(task_id: str | uuid.UUID) -> dict | None:
    tid = uuid.UUID(str(task_id))
    async with AsyncSessionLocal() as session:
        task = (await session.execute(select(StrategyTask).where(StrategyTask.id == tid))).scalar_one_or_none()
        if not task:
            return None
        strat = (await session.execute(select(Strategy).where(Strategy.id == task.strategy_id))).scalar_one_or_none()
        return {
            "id": str(task.id),
            "channel_id": str(task.channel_id),
            "format": task.format.value if task.format else None,
            "topic": task.topic,
            "kind": task.kind,
            "scheduled_date": task.scheduled_date.isoformat() if task.scheduled_date else None,
            "scheduled_time": task.scheduled_time.isoformat() if task.scheduled_time else None,
            "strategy": {
                "primary_topics": strat.primary_topics if strat else [],
                "goal": strat.goal if strat else None,
            },
        }


async def load_content_context(channel_id: str | uuid.UUID) -> dict[str, Any]:
    from db.models import AnalyticsSnapshot, Channel, ChannelDNA, SnapshotType

    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        channel = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()
        dna = (await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))).scalar_one_or_none()
        strat = (
            await session.execute(
                select(Strategy).where(Strategy.channel_id == cid, Strategy.status == StrategyStatus.active)
                .order_by(Strategy.created_at.desc())
            )
        ).scalars().first()
        recent = (
            await session.execute(
                select(GeneratedPost.post_text)
                .where(GeneratedPost.channel_id == cid,
                       GeneratedPost.created_at >= datetime.now(timezone.utc) - timedelta(days=30))
            )
        ).scalars().all()
        comp_posts = (
            await session.execute(
                select(CompetitorPost.text_preview)
                .join(Competitor, CompetitorPost.competitor_id == Competitor.id)
                .where(Competitor.channel_id == cid,
                       CompetitorPost.posted_at >= datetime.now(timezone.utc) - timedelta(days=7))
            )
        ).scalars().all()
        intel_snap = (
            await session.execute(
                select(AnalyticsSnapshot)
                .where(AnalyticsSnapshot.channel_id == cid)
                .order_by(AnalyticsSnapshot.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
    intelligence = (intel_snap.intelligence or {}) if intel_snap else {}
    return {
        "channel_dna": {"tone_fingerprint": dna.tone_fingerprint, "category": dna.category} if dna else {},
        "strategy": {"primary_topics": strat.primary_topics, "goal": strat.goal} if strat else {},
        "score_threshold": channel.score_threshold if channel else settings.SCORE_THRESHOLD,
        "recent_post_fingerprints": [t for t in recent if t],
        "competitor_post_fingerprints": [t for t in comp_posts if t],
        "recycle_candidates": intelligence.get("recycle_candidates") or [],
        "telegram_username": channel.telegram_username if channel else None,
        "auto_approve": bool(channel.auto_approve) if channel else False,
    }


async def fetch_content_sources(channel_id: str | uuid.UUID, topic: str | None = None, format: str | None = None) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(ContentSource)
                .where(ContentSource.channel_id == cid, ContentSource.is_active.is_(True))
                .order_by(ContentSource.avg_quality_score.desc())
            )
        ).scalars().all()
    # Channel Website is always tried first — regardless of EMA drift — so the
    # channel's own content takes priority over generic RSS/Telegram sources.
    sorted_rows = sorted(rows, key=lambda r: (0 if r.name == "Channel Website" else 1, -(r.avg_quality_score or 0.0)))
    return {"sources": [
        {"id": str(r.id), "type": r.type.value, "url": r.url, "name": r.name,
         "avg_quality_score": r.avg_quality_score} for r in sorted_rows
    ]}


async def update_source_quality_score(source_id: str | uuid.UUID, item_score: int) -> dict[str, Any]:
    sid = uuid.UUID(str(source_id))
    async with AsyncSessionLocal() as session:
        row = (await session.execute(select(ContentSource).where(ContentSource.id == sid))).scalar_one_or_none()
        if not row:
            return {"new_avg_quality_score": None, "source_deactivated": False}
        new_avg, new_total = update_source_quality(row.avg_quality_score or 0.0, row.total_items_scored or 0, item_score)
        row.avg_quality_score = new_avg
        row.total_items_scored = new_total
        deactivated = False
        if new_avg < 2.5 and new_total >= 20:
            row.is_active = False
            deactivated = True
        await session.commit()
    return {"new_avg_quality_score": new_avg, "source_deactivated": deactivated}


# ── Item / score persistence ─────────────────────────────────────────────────
async def save_content_item(channel_id: str | uuid.UUID, source_id: str | None, item: dict) -> str:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        row = ContentItem(
            channel_id=cid,
            source_id=uuid.UUID(source_id) if source_id else None,
            external_url=item.get("external_url"),
            title=item.get("title"),
            body_text=item.get("body_text"),
            author=item.get("author"),
            published_at=item.get("published_at"),
            format_tag=item.get("format_tag"),
            topics=item.get("topics"),
            status=ContentItemStatus.scored,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return str(row.id)


async def save_content_score(content_item_id: str, channel_id: str | uuid.UUID, scores: dict) -> str:
    async with AsyncSessionLocal() as session:
        row = ContentScore(
            content_item_id=uuid.UUID(content_item_id),
            channel_id=uuid.UUID(str(channel_id)),
            relevance=scores["relevance"], freshness=scores["freshness"],
            novelty=scores["novelty"], goal_alignment=scores["goal_alignment"],
            virality=scores["virality"], competitor_set=scores["competitor_set"],
            brand_safety=scores["brand_safety"], total_score=scores["total"],
            passed=scores["passed"], threshold_used=scores["threshold_used"],
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return str(row.id)


# ── Generation (LLM, Groq) — format-aware ────────────────────────────────────
_GEN_SYSTEM_TEXT = (
    "You are a Telegram channel copywriter. Write a single Telegram-native post: "
    "under 1024 characters, an emoji opener, a short punchy body, and a clear CTA. "
    "No markdown headers. Match the channel's tone. Be specific and concrete to the "
    "exact topic and category — name real things, avoid generic filler. "
    "IMPORTANT: Write ONLY about the channel's stated niche and primary topics. "
    "Never drift to unrelated subjects (space exploration, generic news, celebrity gossip, "
    "cooking, lifestyle, motivation quotes, or anything outside the channel's niche). "
    "If the source article is off-topic, ignore it and write originally on the given topic. "
    'Reply ONLY as JSON: {"post_text": "...", "cta": "...", "hashtags": ["tag1","tag2"]}.'
)
_GEN_SYSTEM_POLL = (
    "You are a Telegram channel copywriter. Create an engaging poll for the channel. "
    "Write a short question (with an emoji) and 2-4 concise options. Match the tone. "
    "IMPORTANT: The poll MUST be about the channel's stated niche and primary topics only. "
    'Reply ONLY as JSON: {"question": "...", "options": ["...","..."], "hashtags": ["tag1"]}.'
)

# strategy/task formats -> generated post format (PostFormat enum)
_GEN_FORMAT_MAP = {
    "text": "text", "article": "text",
    "poll": "poll",
    "photo": "photo", "meme": "photo", "image": "photo", "carousel": "photo",
    "video": "video",
    "link": "link", "url": "link",
}


def _gen_format(task_format: str | None) -> str:
    return _GEN_FORMAT_MAP.get((task_format or "text").lower(), "text")


def _tone_str(dna: dict) -> str:
    tone = (dna or {}).get("tone_fingerprint") or {}
    if not tone:
        return "neutral"
    return ", ".join(f"{k}:{v}" for k, v in sorted(tone.items(), key=lambda kv: kv[1], reverse=True)[:3])


# Phase 2: habit-loop trigger styles -> extra generation instruction by `kind`.
_KIND_INSTRUCTION = {
    # Phase 2 — habit-loop + recycle trigger styles.
    "series": "This is part of a multi-day SERIES — the day number is in the topic. Briefly recap the previous day, deliver today's installment, and end by teasing the next day so readers return.",
    "cliffhanger": "Write a CLIFFHANGER teaser that opens a loop ('tomorrow I'll show…') without revealing the payoff.",
    "weekly": "Write a recurring WEEKLY ROUNDUP that feels like a regular appointment readers can expect.",
    "challenge": "Frame a 7-DAY CHALLENGE with a clear daily task and an invitation to commit.",
    "reengage": "Write a warm WIN-BACK message asking lapsed members what they want more of.",
    "recycle": "This post RECYCLES a past break-out hit in a NEW format. Keep the core value/hook, refresh the framing, and make it feel new — not a lazy repost.",
}


def _base_user_prompt(task: dict, dna: dict, content_item: dict | None) -> str:
    category = dna.get("category") or "general"
    topics = dna.get("top_topics") or []
    topics_str = ", ".join(str(t) for t in topics[:5]) if topics else category
    p = (
        f"Topic: {task.get('topic')}\n"
        f"Channel niche: {category} | Primary topics ONLY: {topics_str}\n"
        f"Channel tone: {_tone_str(dna)}\n"
    )
    kind_hint = _KIND_INSTRUCTION.get((task.get("kind") or "").lower())
    if kind_hint:
        p += f"Special format: {kind_hint}\n"
    if content_item:
        p += (
            f"\nSource title: {content_item.get('title')}\n"
            f"Source excerpt: {(content_item.get('body_text') or '')[:800]}\n"
        )
    return p


async def _fetch_topic_image_url(topic: str | None, category: str | None = None) -> str | None:
    """Fetch a topic-relevant image from Pexels. Returns URL or None (caller falls back to text).
    Requires PEXELS_API_KEY in settings; silently no-ops without one."""
    if not settings.PEXELS_API_KEY:
        return None
    raw = f"{category or ''} {topic or ''}".strip() or "technology"
    query = re.sub(r"[^a-z0-9 ]", "", raw.lower()).strip()[:100]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": settings.PEXELS_API_KEY},
                params={"query": query, "per_page": 5, "orientation": "landscape"},
            )
            photos = resp.json().get("photos", [])
            if not photos and category:
                cat_q = re.sub(r"[^a-z0-9 ]", "", category.lower()).strip()
                resp2 = await client.get(
                    "https://api.pexels.com/v1/search",
                    headers={"Authorization": settings.PEXELS_API_KEY},
                    params={"query": cat_q, "per_page": 3},
                )
                photos = resp2.json().get("photos", [])
            if photos:
                return photos[0]["src"]["large2x"]
    except Exception:
        pass
    return None


async def _generate(task: dict, dna: dict, content_item: dict | None, is_original: bool) -> dict[str, Any]:
    """Format-aware generation for text / poll / photo / video / link."""
    fmt = _gen_format(task.get("format"))
    media_url = (content_item or {}).get("image_url")
    external_url = (content_item or {}).get("external_url")

    # photo/video slots need media — fetch from Pexels when no source image.
    # If Pexels is unconfigured or returns nothing, downgrade to text so the
    # post still ships rather than publishing a broken photo.
    if fmt in ("photo", "video") and not media_url:
        media_url = await _fetch_topic_image_url(task.get("topic"), dna.get("category"))
        fmt = "photo" if media_url else "text"

    if fmt == "poll":
        raw = await chat_complete(_GEN_SYSTEM_POLL, _base_user_prompt(task, dna, content_item))
        poll = parse_poll_json(raw)
        out = {
            "post_text": poll["question"], "poll_options": poll["options"],
            "cta": "", "hashtags": poll["hashtags"], "media_url": None,
        }
    else:
        user = _base_user_prompt(task, dna, content_item)
        if fmt == "link" and external_url:
            user += f"\nInclude this link in the post: {external_url}\n"
        user += "\nWrite the post."
        raw = await chat_complete(_GEN_SYSTEM_TEXT, user)
        out = parse_post_json(raw)
        out["poll_options"] = None
        out["media_url"] = media_url if fmt in ("photo", "video") else None
        if fmt == "link" and external_url and external_url not in (out["post_text"] or ""):
            out["post_text"] = f"{out['post_text']}\n\n{external_url}"

    out.update({
        "format": fmt, "llm_model": settings.GROQ_MODEL,
        "generation_prompt": _base_user_prompt(task, dna, content_item),
        "is_original": is_original,
    })
    return out


async def generate_post(content_item: dict, task: dict, channel_dna: dict) -> dict[str, Any]:
    return await _generate(task, channel_dna, content_item, is_original=False)


async def generate_original_post(task: dict, channel_dna: dict) -> dict[str, Any]:
    return await _generate(task, channel_dna, None, is_original=True)


# ── Review queue ─────────────────────────────────────────────────────────────
_GEN_FORMATS = {"text", "photo", "video", "poll", "link"}


async def add_to_review_queue(
    channel_id: str | uuid.UUID, generated_post: dict, task: dict, content_item_id: str | None = None
) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    # prefer the format the generator actually produced (may downgrade photo->text)
    fmt = generated_post.get("format") or task.get("format")
    fmt = fmt if fmt in _GEN_FORMATS else "text"
    scheduled_at = _slot_datetime(task)
    async with AsyncSessionLocal() as session:
        gp = GeneratedPost(
            channel_id=cid,
            content_item_id=uuid.UUID(content_item_id) if content_item_id else None,
            strategy_task_id=uuid.UUID(task["id"]) if task.get("id") else None,
            post_text=generated_post.get("post_text"),
            post_format=fmt,
            media_url=generated_post.get("media_url"),
            poll_options=generated_post.get("poll_options"),
            cta=generated_post.get("cta"),
            hashtags=generated_post.get("hashtags"),
            llm_model=generated_post.get("llm_model"),
            generation_prompt=generated_post.get("generation_prompt"),
            review_status=ReviewStatus.pending,
        )
        session.add(gp)
        await session.flush()
        pq = PostQueue(
            channel_id=cid,
            generated_post_id=gp.id,
            strategy_task_id=uuid.UUID(task["id"]) if task.get("id") else None,
            scheduled_at=scheduled_at,
            status=QueueStatus.queued,
        )
        session.add(pq)
        await session.commit()
        return {
            "generated_post_id": str(gp.id),
            "queue_id": str(pq.id),
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "review_status": "pending",
        }


async def maybe_auto_publish(channel_id: str | uuid.UUID, generated_post_id: str) -> dict[str, Any]:
    """If the channel has auto_approve enabled, approve and publish immediately."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        channel = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()
        if not channel or not channel.auto_approve:
            return {"auto_published": False, "reason": "auto_approve_disabled"}
        username = channel.telegram_username
    await update_review_status(generated_post_id, "approved")
    pub = await publish_generated_post(generated_post_id, username)
    return {
        "auto_published": bool(pub.get("published")),
        "published": pub.get("published"),
        "error": pub.get("error"),
        "telegram_message_id": pub.get("telegram_message_id"),
    }


def _pick_recycle_item(task: dict, candidates: list[dict]) -> dict | None:
    """Match a recycle task to a breakout candidate by preview text."""
    topic = (task.get("topic") or "").lower()
    for c in candidates:
        preview = (c.get("text_preview") or c.get("text") or "").lower()
        if preview and preview[:40] in topic:
            return c
    return candidates[0] if candidates else None


async def _verify_url_active(url: str | None) -> bool:
    """Return True if the URL is still reachable (2xx/3xx). Fails open on errors.

    Used before recycling a deal post — if the deal URL returns 4xx the deal
    has expired and the content agent should fetch fresh content instead."""
    if not url:
        return True
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = await c.head(url)
            return r.status_code < 400
    except Exception:
        return True  # network error → assume still live, fail open


def _slot_datetime(task: dict) -> datetime | None:
    # Slot times are stored on the audience clock (LOCAL_TZ), so stamp the queue
    # row's scheduled_at in that timezone too.
    from tools.strategy import LOCAL_TZ

    d, t = task.get("scheduled_date"), task.get("scheduled_time")
    if not d:
        return None
    try:
        dt = datetime.fromisoformat(f"{d}T{t or '00:00'}")
        return dt.replace(tzinfo=LOCAL_TZ)
    except Exception:
        return None


async def get_review_queue(channel_id: str | uuid.UUID) -> dict[str, Any]:
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(GeneratedPost).where(
                    GeneratedPost.channel_id == cid,
                    GeneratedPost.review_status == ReviewStatus.pending,
                )
            )
        ).scalars().all()
        return {"items": [
            {"generated_post_id": str(r.id), "post_text": r.post_text, "cta": r.cta,
             "hashtags": r.hashtags, "format": r.post_format.value if r.post_format else None}
            for r in rows
        ]}


async def update_review_status(post_id: str | uuid.UUID, status: str, edited_text: str | None = None) -> dict[str, Any]:
    pid = uuid.UUID(str(post_id))
    async with AsyncSessionLocal() as session:
        gp = (await session.execute(select(GeneratedPost).where(GeneratedPost.id == pid))).scalar_one_or_none()
        if not gp:
            return {"updated": False}
        gp.review_status = ReviewStatus(status)
        if edited_text is not None:
            gp.edited_text = edited_text
        await session.commit()
    return {"updated": True, "review_status": status}


# ── Publishing (Bot API; needs BOT_TOKEN — Phase 7) ──────────────────────────
async def publish_post(
    channel_username: str,
    post_text: str,
    post_format: str = "text",
    media_url: str | None = None,
    poll_options: list[str] | None = None,
) -> dict[str, Any]:
    """Publish a post via the Bot API, dispatching by format.

    text/link -> sendMessage, photo -> sendPhoto, video -> sendVideo,
    poll -> sendPoll. Falls back to sendMessage if media is missing.
    """
    if not settings.BOT_TOKEN:
        return {"published": False, "error": "BOT_TOKEN not set"}
    from telegram import Bot

    bot = Bot(token=settings.BOT_TOKEN)
    chat = channel_username if channel_username.startswith("@") else f"@{channel_username}"

    try:
        if post_format == "poll" and poll_options and len(poll_options) >= 2:
            msg = await bot.send_poll(chat_id=chat, question=post_text[:300], options=poll_options[:10])
        elif post_format == "photo" and media_url:
            msg = await bot.send_photo(chat_id=chat, photo=media_url, caption=post_text[:1024])
        elif post_format == "video" and media_url:
            msg = await bot.send_video(chat_id=chat, video=media_url, caption=post_text[:1024])
        else:  # text, link, or media-less fallback
            msg = await bot.send_message(chat_id=chat, text=post_text)
    except Exception as exc:  # noqa: BLE001 — surface as error dict, never 500
        # Most common cause: the bot isn't an admin of the channel yet.
        return {"published": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"published": True, "telegram_message_id": msg.message_id}


async def publish_generated_post(
    post_id: str | uuid.UUID, channel_username: str
) -> dict[str, Any]:
    """Publish an approved generated post and mark its queue row ``sent``.

    Loads the post (preferring an operator's ``edited_text``), dispatches it via
    :func:`publish_post`, and on success stamps the matching ``post_queue`` row
    with ``sent`` status, ``published_at`` and the Telegram message id. Returns
    ``{"published": False, "error": "BOT_TOKEN not set"}`` (a safe no-op) when no
    bot token is configured, so callers can stay publish-agnostic.
    """
    pid = uuid.UUID(str(post_id))
    async with AsyncSessionLocal() as session:
        gp = (await session.execute(select(GeneratedPost).where(GeneratedPost.id == pid))).scalar_one_or_none()
        if not gp:
            return {"published": False, "error": "post not found"}
        text = gp.edited_text or gp.post_text or ""
        fmt = gp.post_format.value if gp.post_format else "text"
        result = await publish_post(channel_username, text, fmt, gp.media_url, gp.poll_options)
        if result.get("published"):
            pq = (
                await session.execute(
                    select(PostQueue).where(PostQueue.generated_post_id == pid)
                )
            ).scalars().first()
            if pq:
                pq.status = QueueStatus.sent
                pq.published_at = datetime.now(timezone.utc)
                pq.telegram_message_id = result.get("telegram_message_id")
                await session.commit()
    return result


async def reschedule_post(queue_id: str | uuid.UUID, new_slot_time: str) -> dict[str, Any]:
    qid = uuid.UUID(str(queue_id))
    async with AsyncSessionLocal() as session:
        pq = (await session.execute(select(PostQueue).where(PostQueue.id == qid))).scalar_one_or_none()
        if not pq:
            return {"rescheduled": False}
        pq.scheduled_at = datetime.fromisoformat(new_slot_time)
        await session.commit()
    return {"rescheduled": True}
