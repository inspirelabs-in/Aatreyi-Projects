"""LLM growth-&-retention strategist pass (the "think like a real operator" layer).

The rule engine in ``tools.strategy`` builds the deterministic backbone: how many
posts/day, at what times, retention-trigger placement. This module adds the human
judgement on top — but it does NOT invent content. A real Telegram channel operator
does not decide "post 50% off boAt Airdopes at 11am"; they decide "headphones &
electronics get the most reactions from my audience, so feature that category at my
peak hour" and let the day's actual best deal fill the slot.

So this pass:
  - ranks the CATEGORIES the audience engages with most (from the channel's own
    high-engagement posts + competitors' winning posts) — never specific offers,
    brands, or platforms (no "Amazon"/"Flipkart", no invented discounts),
  - assigns one category + format to each time slot (favourites at peak times,
    with variety so the feed isn't monotone),
  - produces a recommendation engine: concrete GROWTH and RETENTION recommendations.

The content engine later scrapes the real, current best deal/post IN that category.

Everything is best-effort: on ANY error (no API key, bad JSON, timeout) it returns
the rule-based payload unchanged, so the pipeline can never be broken by the LLM.
"""
from __future__ import annotations

import json as _json
import logging
import re
import uuid
from typing import Any

from sqlalchemy import select

from config import settings
from db.base import AsyncSessionLocal
from db.models import ChannelDNA, Competitor, CompetitorPost
from tools.llm import chat_complete
from tools.strategy import _FORMAT_MAP, _TASK_FORMATS, _normalise_to_pct, _DEALS_CATEGORIES

log = logging.getLogger(__name__)

_ALLOWED_SLOT_FORMATS = {"text", "photo", "video", "poll", "link"}
_DEALS_FORMATS = {"photo", "link"}  # broadcast deals: no polls/questions
_MAX_ENRICH_SLOTS = 21


async def _channel_sample_posts(cid: uuid.UUID) -> list[dict]:
    async with AsyncSessionLocal() as session:
        dna = (
            await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))
        ).scalar_one_or_none()
    return list(dna.sample_posts or []) if dna else []


async def _competitor_top_posts(cid: uuid.UUID, limit: int = 12) -> list[dict]:
    """Competitors' highest-ER recent posts — what's actually winning the niche."""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    CompetitorPost.text_preview,
                    CompetitorPost.format,
                    CompetitorPost.er,
                    CompetitorPost.views,
                    Competitor.competitor_username,
                )
                .join(Competitor, CompetitorPost.competitor_id == Competitor.id)
                .where(Competitor.channel_id == cid)
                .order_by(CompetitorPost.er.desc().nulls_last())
                .limit(limit)
            )
        ).all()
    out = []
    for text, fmt, er, views, uname in rows:
        out.append({
            "username": uname,
            "text": (text or "").replace("\n", " ").strip()[:180],
            "format": fmt.value if fmt is not None else None,
            "er": round(er, 2) if er is not None else None,
            "views": views,
        })
    return out


def _deals_vocabulary() -> list[str]:
    """The product-category vocabulary the strategist may choose from for deals."""
    try:
        from tools.deal_scrapers import DEAL_CATEGORIES
        return [c["category"] for c in DEAL_CATEGORIES]
    except Exception:
        return []


def _fmt_posts(posts: list[dict], with_er: bool = False) -> str:
    lines = []
    for p in posts:
        txt = (p.get("text") or "").replace("\n", " ").strip()[:160]
        if not txt:
            continue
        tag = p.get("format") or "text"
        if with_er and p.get("er") is not None:
            who = f"@{p.get('username')}" if p.get("username") else "?"
            lines.append(f"- [{who} · {tag} · {p['er']}% ER] {txt}")
        else:
            note = " (high engagement)" if p.get("_high_er") else ""
            lines.append(f"- [{tag}]{note} {txt}")
    return "\n".join(lines) if lines else "(none available)"


def _canonical_category(name: str, vocab: list[str]) -> str | None:
    """Map a free-text category back onto the allowed vocabulary (case/substring tolerant)."""
    if not name or not vocab:
        return None
    n = name.strip().lower()
    low = {v.lower(): v for v in vocab}
    if n in low:
        return low[n]
    # substring either direction (e.g. "fashion" -> "Fashion Women")
    for v in vocab:
        vl = v.lower()
        if vl in n or n in vl:
            return v
    # token overlap
    n_tok = {w for w in re.findall(r"[a-z0-9]+", n) if len(w) > 2}
    best, score = None, 0
    for v in vocab:
        v_tok = {w for w in re.findall(r"[a-z0-9]+", v.lower()) if len(w) > 2}
        ov = len(n_tok & v_tok)
        if ov > score:
            best, score = v, ov
    return best


def _build_prompt(ctx: dict) -> tuple[str, str]:
    dna = ctx["dna"]
    bench = ctx["benchmark"]
    category = (dna.get("category") or ctx.get("category") or "general")
    is_deals = ctx["is_deals"]
    vocab = ctx["vocab"]
    fmt_rule = (
        "Formats: use ONLY 'photo' or 'link' (this is a broadcast deals channel — it "
        "can't take replies, so NEVER 'poll' or question posts)."
        if is_deals else
        "Formats: choose from text, photo, video, poll, link — favour visual + "
        "interactive formats where the niche rewards them."
    )
    vocab_line = (
        "Choose each slot's category ONLY from this exact list (copy the name verbatim):\n  "
        + ", ".join(vocab)
        if vocab else
        "Choose each slot's category from the channel's own recurring themes."
    )
    slot_lines = "\n".join(
        f'  {s["i"]}: {s["scheduled_date"]} {s["scheduled_time"]}'
        + (f' (purpose: {s["kind"]})' if s.get("kind") else "")
        for s in ctx["slots"]
    )
    system = (
        "You are a senior Telegram channel GROWTH & RETENTION strategist. You are given "
        "a channel's real engagement data, its own best-performing posts, and its "
        "competitors' best posts. Decide the channel's content STRATEGY like a human "
        "operator would.\n"
        "STRICT RULES:\n"
        "1. Work at the level of CATEGORIES/THEMES only. NEVER invent a specific product, "
        "brand, discount, price, or shopping platform (no 'Amazon', 'Flipkart', "
        "'50% off boAt'). The content engine fills each slot with the real, current best "
        "item — your job is only to pick WHICH CATEGORY, WHEN, and in WHAT FORMAT.\n"
        "2. Rank categories by what the AUDIENCE actually engages with (reactions/views) "
        "based on the data below; put the strongest categories in the best (earliest-listed) "
        "slots, and keep VARIETY across the day so the feed isn't monotone.\n"
        "3. Also produce a recommendation engine: concrete GROWTH and RETENTION recommendations.\n"
        "Reply with ONLY a JSON object — no prose, no code fences."
    )
    schema = (
        '{\n'
        '  "audience_insight": "<1-2 sentences: what this audience engages with and why>",\n'
        '  "top_categories": [{"category":"<from the list>","why":"<engagement evidence>"}, ... ranked],\n'
        '  "growth_recommendations": [{"recommendation":"<specific action>","why":"<why it grows subs/reach>"}, ... 2-4],\n'
        '  "retention_recommendations": [{"recommendation":"<specific action>","why":"<why it keeps members>"}, ... 2-4],\n'
        '  "slots": [{"i":<index>,"category":"<from the list>","format":"<allowed format>"}, ... one per slot]\n'
        '}'
    )
    user = (
        f"CHANNEL: @{ctx.get('username')} | category: {category}\n"
        f"Engagement: ER {bench.get('my_avg_er')}% (competitor avg {bench.get('competitor_avg_er')}%, "
        f"target {bench.get('target_er')}%) | subscribers {ctx.get('sub_delta')} "
        f"({ctx.get('sub_delta_pct')}%) | churn: {ctx.get('churn')}\n"
        f"Best posting hour (local): {ctx.get('best_hour')} | best days: {ctx.get('best_days')}\n"
        f"Format engagement (ER by format): {ctx.get('er_by_format')}\n\n"
        f"THE CHANNEL'S OWN POSTS (some marked high engagement):\n{_fmt_posts(ctx['own_posts'])}\n\n"
        f"COMPETITORS' BEST POSTS (highest engagement first):\n"
        f"{_fmt_posts(ctx['competitor_posts'], with_er=True)}\n\n"
        f"{vocab_line}\n{fmt_rule}\n\n"
        f"Assign a category + format to EVERY slot below (keep dates/times as given):\n{slot_lines}\n\n"
        f"Return JSON in EXACTLY this shape:\n{schema}\n\nJSON:"
    )
    return system, user


def _coerce_format(fmt: str | None, is_deals: bool, fallback: str) -> str:
    f = (fmt or "").strip().lower()
    f = _FORMAT_MAP.get(f, f)
    if f not in _ALLOWED_SLOT_FORMATS:
        f = fallback
    if is_deals and f not in _DEALS_FORMATS:
        f = "photo"
    return f if f in _TASK_FORMATS else "text"


def _parse(raw: str) -> dict | None:
    text = raw.strip()
    if "{" in text and "}" in text:
        text = text[text.find("{"): text.rfind("}") + 1]
    try:
        data = _json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _clean_recs(items: Any, limit: int = 4) -> list[dict]:
    out = []
    for it in (items or [])[:limit]:
        if isinstance(it, dict) and it.get("recommendation"):
            out.append({
                "recommendation": str(it.get("recommendation"))[:280],
                "why": str(it.get("why") or "")[:400],
            })
        elif isinstance(it, str) and it.strip():
            out.append({"recommendation": it.strip()[:280], "why": ""})
    return out


async def llm_enrich_strategy(
    channel_id: str | uuid.UUID, payload: dict, inputs: dict
) -> dict:
    """Enrich a rule-based strategy with category-level strategist reasoning +
    a growth/retention recommendation engine. Unchanged on any failure."""
    if not getattr(settings, "GROQ_API_KEY", None):
        return payload
    tasks = payload.get("tasks") or []
    if not tasks:
        return payload
    try:
        cid = uuid.UUID(str(channel_id))
        dna = inputs.get("dna") or {}
        category = dna.get("category") or (inputs.get("channel") or {}).get("category")
        is_deals = (category or "").lower().strip() in _DEALS_CATEGORIES

        # category vocabulary the strategist must pick from
        if is_deals:
            vocab = _deals_vocabulary()
        else:
            vocab = list(dict.fromkeys(
                (dna.get("top_topics") or []) + (payload.get("primary_topics") or [])
            ))

        own_posts = await _channel_sample_posts(cid)
        for rc in (inputs.get("recycle_candidates") or [])[:4]:
            own_posts.append({"text": rc.get("text") or rc.get("text_preview"),
                              "format": None, "_high_er": True})
        competitor_posts = await _competitor_top_posts(cid)
        analytics = inputs.get("analytics_daily") or inputs.get("analytics_weekly") or {}

        enrich_slots = tasks[:_MAX_ENRICH_SLOTS]
        slots_meta = [
            {"i": i, "scheduled_date": t["scheduled_date"],
             "scheduled_time": t["scheduled_time"], "kind": t.get("kind")}
            for i, t in enumerate(enrich_slots)
        ]
        ctx = {
            "username": (inputs.get("channel") or {}).get("username"),
            "category": category, "is_deals": is_deals, "vocab": vocab,
            "dna": dna, "benchmark": payload.get("benchmark") or {},
            "sub_delta": analytics.get("subscriber_delta"),
            "sub_delta_pct": analytics.get("subscriber_delta_pct"),
            "churn": analytics.get("churn_signal"),
            "best_hour": dna.get("best_post_hour"), "best_days": dna.get("best_post_days"),
            "er_by_format": inputs.get("er_by_format"),
            "own_posts": own_posts, "competitor_posts": competitor_posts,
            "slots": slots_meta,
        }
        system, user = _build_prompt(ctx)
        raw = await chat_complete(system, user, max_tokens=1800, temperature=0.4)
        data = _parse(raw)
        if not data:
            log.warning("strategy_llm: unparseable response for %s, keeping rule-based", cid)
            return payload

        # ── recommendation engine + diagnosis ──
        if isinstance(data.get("audience_insight"), str) and data["audience_insight"].strip():
            payload["diagnosis"] = data["audience_insight"].strip()
        growth_recs = _clean_recs(data.get("growth_recommendations"))
        retention_recs = _clean_recs(data.get("retention_recommendations"))
        if growth_recs:
            payload["growth_recommendations"] = growth_recs
        if retention_recs:
            payload["retention_recommendations"] = retention_recs

        # ── ranked categories -> primary_topics (canonicalised to the vocab) ──
        ranked = []
        for c in (data.get("top_categories") or []):
            nm = c.get("category") if isinstance(c, dict) else c
            canon = _canonical_category(str(nm or ""), vocab) if vocab else (str(nm).strip() or None)
            if canon and canon not in ranked:
                ranked.append(canon)
        if ranked:
            payload["primary_topics"] = ranked[:6]

        # ── per-slot category + format (category ONLY — content engine fills the item) ──
        by_i = {s["i"]: s for s in (data.get("slots") or [])
                if isinstance(s, dict) and isinstance(s.get("i"), int)}
        rr = ranked or payload.get("primary_topics") or []
        assigned = 0
        for i, task in enumerate(enrich_slots):
            s = by_i.get(i)
            cat = None
            if s:
                cat = _canonical_category(str(s.get("category") or ""), vocab) if vocab \
                    else (str(s.get("category") or "").strip() or None)
                if not task.get("kind"):
                    task["format"] = _coerce_format(s.get("format"), is_deals,
                                                    task.get("format") or "text")
            if not cat and rr:
                cat = rr[i % len(rr)]  # round-robin favourites when LLM skipped a slot
            if cat:
                task["topic"] = cat[:128]   # category name ONLY — no offers/brands/prices
                assigned += 1

        # keep content_mix consistent with the (possibly changed) slot formats
        counts: dict[str, float] = {}
        for t in tasks:
            counts[t.get("format") or "text"] = counts.get(t.get("format") or "text", 0.0) + 1.0
        new_mix = _normalise_to_pct(counts)
        if new_mix:
            payload["content_mix"] = new_mix

        payload["strategist"] = "llm"
        log.info("strategy_llm: %s -> %d categories ranked, %d/%d slots assigned, %dG/%dR recs",
                 cid, len(ranked), assigned, len(enrich_slots), len(growth_recs), len(retention_recs))
        return payload
    except Exception as exc:  # noqa: BLE001 — never let the LLM break strategy
        log.warning("strategy_llm: enrich failed (%s: %s), keeping rule-based",
                    type(exc).__name__, exc)
        return payload
