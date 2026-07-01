"""Competitor Intelligence engine (per competitor_intelligence.md).

Pure analysis + a per-competitor LLM pass. Produces INTELLIGENCE ONLY (facts and
structured analysis) — never recommendations. The Strategy Engine consumes this.

Pieces:
  - weighted similarity sub-scores (Audience 35 / Topic 25 / Lang-Region 20 /
    Format 10 / Freq 5 / Size 5) — audience/language are approximated from the
    signals we actually have and flagged as such (we never invent evidence).
  - classification: direct | aspirational | adjacent
  - per-competitor analysis from their posts: media mix %, best posting hours,
    avg views/ER, top posts; plus an LLM pass for CTA patterns, writing style,
    strengths, weaknesses, and why the top posts won.
  - channel-level intelligence: content gaps, emerging trends, best schedule,
    best media mix, best CTA, opportunities (facts, not recommendations).
"""
from __future__ import annotations

import json as _json
import logging
import re
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, ChannelDNA
from tools.llm import chat_complete

log = logging.getLogger(__name__)

# Spec weights (sum = 1.0).
W = {"audience": 0.35, "topic": 0.25, "language_region": 0.20,
     "format": 0.10, "frequency": 0.05, "size": 0.05}

_STOP = {"the", "and", "for", "with", "you", "your", "this", "that", "are", "from",
         "now", "get", "all", "new", "out", "off", "https", "http", "www", "com",
         # generic filler / CTA noise that is never an "emerging trend"
         "here", "read", "more", "click", "tap", "link", "use", "only", "today",
         "just", "grab", "shop", "buy", "order", "check", "want", "will", "have",
         "was", "not", "but", "our", "them", "they", "one", "two", "top", "best",
         # deal-domain words that are ALWAYS present on a deals channel — constant,
         # not a trend (their presence tells us nothing new)
         "deal", "deals", "price", "prices", "offer", "offers", "discount",
         "discounts", "sale", "code", "coupon", "coupons", "cashback", "free",
         "flat", "upto", "onwards", "save", "lowest", "amazon", "flipkart",
         "myntra", "ajio", "meesho", "amzn", "flpkrt", "rupees", "rupee"}

try:
    from tools.strategy import LOCAL_TZ
except Exception:  # pragma: no cover
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Kolkata")


async def load_my_profile(channel_id: str | uuid.UUID) -> dict[str, Any]:
    """The managed channel's reference profile for similarity scoring."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == cid))).scalar_one_or_none()
        dna = (await s.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))).scalar_one_or_none()
    fmts = {}
    for f in ((dna.top_content_formats if dna else None) or []):
        if isinstance(f, dict) and f.get("format"):
            fmts[str(f["format"]).lower()] = float(f.get("share") or 0)
    return {
        "category": (dna.category if dna else None) or (ch.category if ch else None),
        "sub_category": (dna.sub_category if dna else None),
        "top_topics": [str(t).lower() for t in ((dna.top_topics if dna else None) or [])],
        "formats": fmts,
        "post_frequency_per_day": (dna.post_frequency_per_day if dna else None),
        "subscriber_count": (dna.subscriber_count if dna else None) or (ch and None),
        "language": (ch.language if ch else None) or "en",
    }


# ── post-level analysis (pure) ───────────────────────────────────────────────
def _post_format(p: dict) -> str:
    f = (p.get("format") or "text")
    return f.value if hasattr(f, "value") else str(f)


def media_mix(posts: list[dict]) -> dict[str, float]:
    """% share of each format across a competitor's posts."""
    if not posts:
        return {}
    c = Counter(_post_format(p) for p in posts)
    total = sum(c.values()) or 1
    return {k: round(v / total * 100) for k, v in c.most_common()}


def best_hours(posts: list[dict], top: int = 3) -> list[int]:
    """Most common local posting hours (audience clock)."""
    hours = []
    for p in posts:
        dt = p.get("posted_at")
        if dt is None:
            continue
        try:
            hours.append(dt.astimezone(LOCAL_TZ).hour)
        except Exception:
            hours.append(getattr(dt, "hour", None))
    hours = [h for h in hours if h is not None]
    return [h for h, _ in Counter(hours).most_common(top)]


def _er(p: dict) -> float:
    e = p.get("er")
    if e is not None:
        return float(e)
    views = p.get("views") or 0
    eng = (p.get("reactions") or p.get("reactions_count") or 0) + (p.get("forwards") or 0)
    return eng / max(views, 1) * 100.0


def analyze_posts(posts: list[dict], top_n: int = 5) -> dict[str, Any]:
    """Computed (no-LLM) per-competitor analysis from their posts."""
    posts = posts or []
    views = [p.get("views") or 0 for p in posts]
    top = sorted(posts, key=_er, reverse=True)[:top_n]
    return {
        "media_mix": media_mix(posts),
        "best_hours": best_hours(posts),
        "avg_views": round(sum(views) / len(views)) if views else None,
        "posts_analyzed": len(posts),
        "top_posts": [
            {"text": (p.get("text_preview") or p.get("text") or "")[:200],
             "format": _post_format(p), "er": round(_er(p), 2)}
            for p in top
        ],
    }


# ── similarity sub-scores (pure) ─────────────────────────────────────────────
def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _proximity(a: float | None, b: float | None) -> float:
    if not a or not b:
        return 0.5  # unknown -> neutral
    lo, hi = min(a, b), max(a, b)
    return round(lo / hi, 3) if hi else 0.5


def _format_overlap(my_fmts: dict, cand_mix: dict) -> float:
    """Overlap of two format distributions (sum of per-format minimum share)."""
    if not my_fmts or not cand_mix:
        return 0.5
    # normalise both to fractions
    a = {k: v / (sum(my_fmts.values()) or 1) for k, v in my_fmts.items()}
    b = {k: v / (sum(cand_mix.values()) or 1) for k, v in cand_mix.items()}
    return round(sum(min(a.get(k, 0), b.get(k, 0)) for k in set(a) | set(b)), 3)


def similarity_breakdown(my: dict, cand: dict) -> dict[str, Any]:
    """Weighted similarity per spec. cand needs: topic_similarity, candidate_topics,
    media_mix, post_frequency_per_day, subscriber_count, language."""
    topic = cand.get("topic_similarity")
    if topic is None:
        topic = round(_jaccard(set(my.get("top_topics") or []),
                               {str(t).lower() for t in (cand.get("candidate_topics") or [])}), 3)
    fmt = _format_overlap(my.get("formats") or {}, cand.get("media_mix") or {})
    freq = _proximity(my.get("post_frequency_per_day"), cand.get("post_frequency_per_day"))
    size = _proximity(my.get("subscriber_count"), cand.get("subscriber_count"))
    # language/region: same language -> 1.0; unknown -> approximate (same discovery region).
    cand_lang = (cand.get("language") or my.get("language") or "en")
    lang = 1.0 if cand_lang == (my.get("language") or "en") else 0.5
    # audience: no demographic feed -> APPROXIMATED from topic overlap + size tier + category.
    cat_match = 1.0 if (cand.get("category") and cand.get("category") == my.get("category")) else 0.5
    audience = round(0.5 * topic + 0.3 * size + 0.2 * cat_match, 3)
    subs = {"audience": audience, "topic": round(topic, 3), "language_region": lang,
            "format": fmt, "frequency": freq, "size": size}
    total = round(sum(W[k] * subs[k] for k in W) * 100, 1)
    return {**subs, "total": total, "approximated": ["audience", "language_region"]}


def classify(topic_sim: float | None, my_subs: int | None, cand_subs: int | None) -> str:
    """direct | aspirational | adjacent."""
    t = topic_sim or 0.0
    ratio = (cand_subs / my_subs) if (my_subs and cand_subs) else None
    if ratio is not None:
        if t >= 0.45 and 0.5 <= ratio <= 2.5:
            return "direct"
        if t >= 0.35 and ratio > 2.5:
            return "aspirational"
        return "adjacent"
    return "direct" if t >= 0.5 else "adjacent"


# ── per-competitor LLM analysis ──────────────────────────────────────────────
async def llm_analyze_competitor(name: str, category: str | None, top_posts: list[dict]) -> dict[str, Any]:
    """One LLM call -> CTA patterns, writing style, strengths, weaknesses, why-won.
    INTELLIGENCE ONLY (no recommendations). {} on any failure."""
    posts = [p for p in (top_posts or []) if p.get("text")]
    if not posts:
        return {}
    corpus = "\n".join(f"- [{p.get('format')} · {p.get('er')}% ER] {p['text'][:160]}" for p in posts[:6])
    system = (
        "You are a competitor analyst for Telegram channels. Analyse the competitor's "
        "best posts and return STRUCTURED FACTS ONLY — describe what they do, never give "
        "advice or recommendations. Reply with ONLY a JSON object, no prose."
    )
    schema = (
        '{"cta_patterns":["<observed CTA type>", ...],'
        '"writing_style":"<short factual description>",'
        '"strengths":["<fact>", ... up to 3],'
        '"weaknesses":["<fact>", ... up to 3],'
        '"why_top_posts":["<why this post likely performed>", ...up to 3]}'
    )
    user = f"Competitor: {name} (category: {category})\nTop posts:\n{corpus}\n\nReturn JSON:\n{schema}\n\nJSON:"
    try:
        raw = await chat_complete(system, user, max_tokens=500, temperature=0.3)
        text = raw.strip()
        if "{" in text and "}" in text:
            text = text[text.find("{"): text.rfind("}") + 1]
        data = _json.loads(text)
        if not isinstance(data, dict):
            return {}
        def _lst(x):
            return [str(i).strip()[:140] for i in (x or []) if str(i).strip()][:3]
        return {
            "cta_patterns": _lst(data.get("cta_patterns")),
            "writing_style": str(data.get("writing_style") or "")[:200],
            "strengths": _lst(data.get("strengths")),
            "weaknesses": _lst(data.get("weaknesses")),
            "why_top_posts": _lst(data.get("why_top_posts")),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("llm_analyze_competitor(%s) failed: %s", name, exc)
        return {}


# ── channel-level intelligence (pure aggregation; facts only) ────────────────
def build_channel_intelligence(competitors: list[dict], my: dict) -> dict[str, Any]:
    """Aggregate per-competitor analysis into channel-level intelligence.
    FACTS ONLY (content gaps, emerging trends, best schedule/media-mix/CTA,
    opportunities phrased as observations) — no recommendations."""
    my_topics = set(my.get("top_topics") or [])
    # content gaps: themes competitors cover that we don't
    comp_themes: Counter = Counter()
    cta: Counter = Counter()
    hours: Counter = Counter()
    media_acc: Counter = Counter()
    trend_words: Counter = Counter()
    for c in competitors:
        for t in (c.get("top_themes") or c.get("top_content_themes") or []):
            comp_themes[str(t).lower()] += 1
        intel = c.get("intelligence") or {}
        for p in (intel.get("cta_patterns") or []):
            cta[p.lower()] += 1
        for h in (intel.get("best_hours") or []):
            hours[h] += 1
        for fmt, pct in (intel.get("media_mix") or {}).items():
            media_acc[fmt] += pct
        for p in (intel.get("top_posts") or []):
            for w in re.findall(r"[a-z][a-z0-9]{3,}", (p.get("text") or "").lower()):
                if w not in _STOP:
                    trend_words[w] += 1
    # A real gap = a theme covered by MULTIPLE competitors that we don't touch —
    # not a one-off theme from a single channel's noise.
    gaps = [t for t, cnt in comp_themes.most_common() if cnt >= 2 and t not in my_topics][:6]
    best_media = {k: round(v / max(len(competitors), 1)) for k, v in media_acc.most_common(5)}
    opportunities: list[str] = []
    if gaps:
        opportunities.append(f"Competitors consistently cover {', '.join(gaps[:3])} — limited/absent on this channel.")
    if hours:
        top_h = ", ".join(f"{h:02d}:00" for h, _ in hours.most_common(3))
        opportunities.append(f"Competitors post most at {top_h} (audience-active windows).")
    if best_media:
        lead = max(best_media, key=best_media.get)
        opportunities.append(f"'{lead}' is the dominant format among competitors (~{best_media[lead]}% of their posts).")
    if cta:
        opportunities.append(f"Most common competitor CTAs: {', '.join(p for p, _ in cta.most_common(3))}.")
    return {
        "content_gaps": gaps,
        # Only surface words that recur (>=3x) after filtering domain/noise words —
        # otherwise return nothing rather than junk like "here"/"amzn"/"read".
        "emerging_trends": [w for w, cnt in trend_words.most_common(8) if cnt >= 3],
        "best_schedule": [h for h, _ in hours.most_common(4)],
        "best_media_mix": best_media,
        "best_cta": [p for p, _ in cta.most_common(4)],
        "opportunities": opportunities,
    }
