"""LLM growth-&-retention strategist pass (the "think like a real operator" layer).

The rule engine in ``tools.strategy`` builds the deterministic backbone: how many
posts/day, at what times, retention placement. This module adds the human judgement
on top — but it does NOT invent content and it does NOT place individual posts by
hand. A real operator decides two things:

  1. WHICH CATEGORIES this audience engages with most (the hard judgement), and
  2. concrete GROWTH and RETENTION recommendations.

So the LLM only returns a *ranked list of categories* (8-12, drawn from a fixed
vocabulary — never invented products/brands/discounts, never "Amazon"/"Flipkart")
plus the recommendations. Deterministic code then spreads those categories across
EVERY slot of the plan (round-robin → real variety, favourites first), so no slot
can ever fall back to a hallucinated topic. The content engine fills each slot with
the real, current best item in that category.

Best-effort: on ANY error it returns the rule-based payload unchanged.
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

_DEALS_FORMATS = {"photo", "link"}  # broadcast deals: no polls/questions
_MIN_CATEGORIES = 8                 # demand real variety, not 2-3 repeated
_MAX_CATEGORIES = 12


async def _channel_sample_posts(cid: uuid.UUID) -> list[dict]:
    async with AsyncSessionLocal() as session:
        dna = (
            await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))
        ).scalar_one_or_none()
    return list(dna.sample_posts or []) if dna else []


async def _competitor_top_posts(cid: uuid.UUID, limit: int = 12) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    CompetitorPost.text_preview, CompetitorPost.format,
                    CompetitorPost.er, Competitor.competitor_username,
                )
                .join(Competitor, CompetitorPost.competitor_id == Competitor.id)
                .where(Competitor.channel_id == cid)
                .order_by(CompetitorPost.er.desc().nulls_last())
                .limit(limit)
            )
        ).all()
    return [{"username": u, "text": (t or "").replace("\n", " ").strip()[:160],
             "format": f.value if f is not None else None,
             "er": round(e, 2) if e is not None else None}
            for t, f, e, u in rows]


def _deals_vocabulary() -> list[str]:
    try:
        from tools.deal_scrapers import DEAL_CATEGORIES
        return [c["category"] for c in DEAL_CATEGORIES]
    except Exception:
        return []


def _fmt_posts(posts: list[dict], with_er: bool = False) -> str:
    lines = []
    for p in posts:
        txt = (p.get("text") or "").replace("\n", " ").strip()[:150]
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


def _fmt_competitor_intel(ci: dict | None) -> str:
    """Competitor intelligence facts for the strategist to ground recommendations."""
    if not ci:
        return ""
    parts = []
    if ci.get("content_gaps"):
        parts.append(f"- Content gaps (competitors cover, we don't): {', '.join(ci['content_gaps'][:6])}")
    if ci.get("emerging_trends"):
        parts.append(f"- Emerging trends in competitor posts: {', '.join(ci['emerging_trends'][:6])}")
    if ci.get("best_schedule"):
        parts.append(f"- Competitor peak hours: {', '.join(f'{h:02d}:00' for h in ci['best_schedule'][:4])}")
    if ci.get("best_media_mix"):
        parts.append(f"- Competitor media mix: {ci['best_media_mix']}")
    for o in (ci.get("opportunities") or [])[:4]:
        parts.append(f"- {o}")
    return ("COMPETITOR INTELLIGENCE (use as evidence for recommendations):\n"
            + "\n".join(parts) + "\n\n") if parts else ""


def _canonical_category(name: str, vocab: list[str]) -> str | None:
    if not name:
        return None
    if not vocab:
        return name.strip() or None
    n = name.strip().lower()
    low = {v.lower(): v for v in vocab}
    if n in low:
        return low[n]
    for v in vocab:
        if v.lower() in n or n in v.lower():
            return v
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
    vocab = ctx["vocab"]
    vocab_line = (
        "Pick categories ONLY from this exact list (copy names verbatim):\n  "
        + ", ".join(vocab)
        if vocab else
        "Pick categories from the channel's own recurring content themes."
    )
    system = (
        "You are a senior Telegram channel GROWTH & RETENTION strategist. Given a "
        "channel's real engagement data, its own best posts, and competitors' best "
        "posts, decide its content strategy like a human operator.\n"
        "STRICT RULES:\n"
        "1. Work at the level of CATEGORIES/THEMES only. NEVER invent a specific product, "
        "brand, price, discount, or platform (no 'Amazon', 'Flipkart', '50% off boAt').\n"
        f"2. Return a RANKED list of {_MIN_CATEGORIES}-{_MAX_CATEGORIES} DISTINCT categories "
        "this audience engages with most (most-engaging first). Use real VARIETY — do not "
        "return just 2-3. Base the ranking on the engagement evidence below.\n"
        "3. Also give concrete GROWTH and RETENTION recommendations.\n"
        "Reply with ONLY a JSON object — no prose, no code fences."
    )
    schema = (
        '{\n'
        '  "audience_insight": "<1-2 sentences: what this audience engages with and why>",\n'
        f'  "ranked_categories": ["<cat1>", "<cat2>", ... {_MIN_CATEGORIES}-{_MAX_CATEGORIES} distinct, best first],\n'
        '  "growth_recommendations": [{"recommendation":"<action>","why":"<why it grows subs/reach>"}, ... 2-4],\n'
        '  "retention_recommendations": [{"recommendation":"<action>","why":"<why it keeps members>"}, ... 2-4]\n'
        '}'
    )
    user = (
        f"CHANNEL: @{ctx.get('username')} | category: {category}\n"
        f"Engagement: ER {bench.get('my_avg_er')}% (competitor avg {bench.get('competitor_avg_er')}%, "
        f"target {bench.get('target_er')}%) | subscribers {ctx.get('sub_delta')} "
        f"({ctx.get('sub_delta_pct')}%) | churn: {ctx.get('churn')}\n"
        f"Best posting hour (local): {ctx.get('best_hour')} | format engagement: {ctx.get('er_by_format')}\n\n"
        f"THE CHANNEL'S OWN POSTS (some marked high engagement):\n{_fmt_posts(ctx['own_posts'])}\n\n"
        f"COMPETITORS' BEST POSTS (highest engagement first):\n"
        f"{_fmt_posts(ctx['competitor_posts'], with_er=True)}\n\n"
        f"{_fmt_competitor_intel(ctx.get('competitor_intelligence'))}"
        f"{vocab_line}\n\n"
        f"Return JSON in EXACTLY this shape:\n{schema}\n\nJSON:"
    )
    return system, user


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
            out.append({"recommendation": str(it["recommendation"])[:280],
                        "why": str(it.get("why") or "")[:400]})
        elif isinstance(it, str) and it.strip():
            out.append({"recommendation": it.strip()[:280], "why": ""})
    return out


async def llm_enrich_strategy(
    channel_id: str | uuid.UUID, payload: dict, inputs: dict
) -> dict:
    """Rank the categories the audience engages with + produce growth/retention
    recommendations, then spread those categories across EVERY slot. Returns the
    payload unchanged on any failure."""
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
        ctx = {
            "username": (inputs.get("channel") or {}).get("username"),
            "category": category, "vocab": vocab,
            "dna": dna, "benchmark": payload.get("benchmark") or {},
            "sub_delta": analytics.get("subscriber_delta"),
            "sub_delta_pct": analytics.get("subscriber_delta_pct"),
            "churn": analytics.get("churn_signal"),
            "best_hour": dna.get("best_post_hour"),
            "er_by_format": inputs.get("er_by_format"),
            "own_posts": own_posts, "competitor_posts": competitor_posts,
            "competitor_intelligence": payload.get("competitor_intelligence"),
        }
        system, user = _build_prompt(ctx)
        raw = await chat_complete(system, user, max_tokens=900, temperature=0.4)
        data = _parse(raw)
        if not data:
            log.warning("strategy_llm: unparseable response for %s, keeping rule-based", cid)
            return payload

        # ── ranked categories (canonicalised to the vocab, distinct) ──
        ranked: list[str] = []
        for nm in (data.get("ranked_categories") or []):
            canon = _canonical_category(str(nm or ""), vocab)
            if canon and canon not in ranked:
                ranked.append(canon)
        if not ranked:
            log.warning("strategy_llm: no usable categories for %s, keeping rule-based", cid)
            return payload
        ranked = ranked[:_MAX_CATEGORIES]

        # ── recommendation engine + audience insight ──
        if isinstance(data.get("audience_insight"), str) and data["audience_insight"].strip():
            payload["diagnosis"] = data["audience_insight"].strip()
        gr = _clean_recs(data.get("growth_recommendations"))
        rr = _clean_recs(data.get("retention_recommendations"))
        if gr:
            payload["growth_recommendations"] = gr
        if rr:
            payload["retention_recommendations"] = rr
        payload["primary_topics"] = ranked[:8]

        # ── spread categories across slots (round-robin → variety, favourites
        #    first). No slot keeps a rule-based/DNA topic, so nothing hallucinated. ──
        if is_deals:
            # Deals slots are an EXECUTION PLAN: loot slots aggregate many categories
            # (topic "Multiple", no image) and single slots target one category with
            # a photo. Only re-assign categories to SINGLE slots — never touch loot
            # slots or the execution fields (kind/format/media/marketplace/scrape_at).
            ci = 0
            for task in tasks:
                if (task.get("kind") or "").lower() == "single":
                    cat = ranked[ci % len(ranked)][:128]
                    ci += 1
                    old = task.get("topic")
                    task["topic"] = cat
                    # keep the rationale category label in sync when it named the old one
                    if old and task.get("rationale") and old in task["rationale"]:
                        task["rationale"] = task["rationale"].replace(old, cat, 1)
            # refresh the UI plan projection from the (now LLM-ranked) slots
            try:
                from tools.strategy import _deals_plan_display
                payload["deals_plan"] = _deals_plan_display(tasks)
            except Exception:
                pass
        else:
            for i, task in enumerate(tasks):
                task["topic"] = ranked[i % len(ranked)][:128]

        # keep content_mix consistent with the actual slot formats
        counts: dict[str, float] = {}
        for t in tasks:
            counts[t.get("format") or "text"] = counts.get(t.get("format") or "text", 0.0) + 1.0
        new_mix = _normalise_to_pct(counts)
        if new_mix:
            payload["content_mix"] = new_mix

        payload["strategist"] = "llm"
        log.info("strategy_llm: %s -> %d categories across %d slots, %dG/%dR recs",
                 cid, len(ranked), len(tasks), len(gr), len(rr))
        return payload
    except Exception as exc:  # noqa: BLE001 — never let the LLM break strategy
        log.warning("strategy_llm: enrich failed (%s: %s), keeping rule-based",
                    type(exc).__name__, exc)
        return payload
