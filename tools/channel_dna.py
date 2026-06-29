"""Channel DNA tools (Phase 2).

Pure, rule-based metric computation per formulae.md §1, plus TGStat fetch and
DB persistence. compute_channel_dna does no I/O so it is fully unit-testable.

Note on ER: formulae.md §1.1 is authoritative —
    ER_post = (reactions + forwards + replies) / min(views, subscriber_count) * 100
(The roadmap's one-line `avg_views/members` summary is superseded by this.)
"""
from __future__ import annotations

import uuid
from collections import defaultdict
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select

from config import settings
from db.base import AsyncSessionLocal
from db.models import ChannelDNA, Tier

# Minimum posts in-window to compute real metrics (formulae.md §1.1).
MIN_POSTS_FOR_DNA = 5
# Agent-level gate (prompts_&_tools.md): below this -> save partial, skip compute.
MIN_POSTS_AGENT_GATE = 10
DNA_WINDOW_DAYS = 30
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ── Tone wordlists (formulae.md §1.6) ────────────────────────────────────────
TONE_WORDLISTS: dict[str, set[str]] = {
    "formal": {
        "therefore", "however", "furthermore", "regarding", "pursuant",
        "accordingly", "hereby", "moreover", "consequently", "notably",
        "official", "announcement", "statement", "report",
    },
    "casual": {
        "hey", "guys", "lol", "gonna", "wanna", "yeah", "cool", "btw",
        "stuff", "kinda", "ok", "okay", "vibe", "chill", "folks",
    },
    "humorous": {
        "lol", "lmao", "haha", "funny", "joke", "meme", "rofl", "hilarious",
        "😂", "🤣", "kidding", "savage",
    },
    "educational": {
        "learn", "understand", "explained", "guide", "how", "why", "tutorial",
        "tips", "lesson", "study", "fact", "knowledge", "example", "step",
    },
    "motivational": {
        "achieve", "success", "growth", "goal", "dream", "inspire",
        "motivation", "discipline", "win", "believe", "hustle", "mindset",
        "powerful", "unlock",
    },
}

# ── Category keyword rules (get_channel_category) ────────────────────────────
CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "deals": {"deal", "deals", "coupon", "coupons", "offer", "offers", "discount", "discounts",
              "sale", "cashback", "promo", "promocode", "voucher", "loot", "flat", "off", "% off",
              "lowest price", "best price", "save", "freebie", "steal"},
    "shopping": {"amazon", "flipkart", "myntra", "ajio", "meesho", "shopping", "cart", "order",
                 "buy now", "price", "store", "online shopping", "ecommerce"},
    "crypto": {"crypto", "bitcoin", "btc", "ethereum", "eth", "blockchain", "web3", "defi", "nft", "token"},
    "tech": {"tech", "ai", "software", "startup", "saas", "gadget", "app", "developer", "coding", "programming"},
    "finance": {"finance", "stock", "market", "investing", "trading", "mutual fund", "nifty", "sensex", "ipo", "money"},
    "news": {"news", "breaking", "update", "headline", "report", "today", "live"},
    "sports": {"sports", "cricket", "football", "match", "ipl", "score", "tournament", "league"},
    "entertainment": {"movie", "film", "music", "celebrity", "bollywood", "series", "trailer", "song",
                       "entertainment", "actor", "actress", "ott", "netflix", "episode", "box office"},
    "education": {"exam", "study", "course", "tutorial", "learn", "upsc", "neet", "jee", "notes", "syllabus"},
    "health": {"health", "fitness", "diet", "workout", "wellness", "nutrition", "yoga", "medical"},
    "gaming": {"gaming", "game", "esports", "pubg", "valorant", "stream", "gamer"},
    "business": {"business", "entrepreneur", "marketing", "growth", "sales", "brand", "ecommerce"},
}


# ── Tier ─────────────────────────────────────────────────────────────────────
def detect_tier(member_count: int | None) -> str:
    """Tier A/B/C mapped to DB enum: new (<5k), mid (<50k), established (>=50k)."""
    n = member_count or 0
    if n < 5000:
        return Tier.new.value
    if n < 50000:
        return Tier.mid.value
    return Tier.established.value


# ── Category ─────────────────────────────────────────────────────────────────
def _compile_keyword(kw: str) -> re.Pattern:
    """Whole-word (or whole-phrase) matcher for a category keyword.

    Uses alphanumeric boundaries instead of str.count so short keywords like
    "ai" or "off" match only the standalone word — NOT substrings inside
    "again"/"email"/"offer" — which otherwise wildly inflate a category's score.
    Internal spaces match any whitespace run so "buy now"/"% off" still match.
    """
    body = re.escape(kw).replace(r"\ ", r"\s+")
    left = r"(?<![a-z0-9])" if kw[:1].isalnum() else ""
    right = r"(?![a-z0-9])" if kw[-1:].isalnum() else ""
    return re.compile(left + body + right, re.IGNORECASE)


_CATEGORY_PATTERNS: dict[str, list[re.Pattern]] = {
    cat: [_compile_keyword(kw) for kw in kws] for cat, kws in CATEGORY_KEYWORDS.items()
}


def get_channel_category(posts_sample: list[dict], username: str | None = None) -> tuple[str | None, str | None]:
    """Keyword-rule category detection from post text (+ optional username)."""
    corpus = " ".join((p.get("text") or "") for p in posts_sample).lower()
    if username:
        corpus += " " + username.lower()
    scores = {
        cat: sum(len(pat.findall(corpus)) for pat in pats)
        for cat, pats in _CATEGORY_PATTERNS.items()
    }
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked or ranked[0][1] == 0:
        return None, None
    category = ranked[0][0]
    sub_category = ranked[1][0] if len(ranked) > 1 and ranked[1][1] > 0 else None
    return category, sub_category


# ── Disappearing messages flag ───────────────────────────────────────────────
def get_disappearing_message_flag(channel_info: dict) -> bool:
    return bool(channel_info.get("has_disappearing_messages"))


# ── Per-post ER (formulae.md §1.1) ───────────────────────────────────────────
def _er_post(post: dict, subscriber_count: int | None) -> float | None:
    views = post.get("views") or 0
    if views <= 0:
        return None  # cannot compute ER without views
    views_capped = min(views, subscriber_count) if subscriber_count else views
    if views_capped <= 0:
        return None
    engagement = (post.get("reactions") or 0) + (post.get("forwards") or 0) + (post.get("replies") or 0)
    return engagement / views_capped * 100.0


def _tone_fingerprint(posts: list[dict]) -> dict[str, float]:
    """Mean per-post tone score, normalised to sum 1.0 (formulae.md §1.6)."""
    per_tone_means: dict[str, float] = {t: 0.0 for t in TONE_WORDLISTS}
    counted = 0
    accum: dict[str, float] = defaultdict(float)
    for p in posts:
        text = (p.get("text") or "").lower()
        tokens = [tok for tok in text.replace("\n", " ").split() if tok]
        total = len(tokens)
        if total == 0:
            continue
        counted += 1
        token_set = set(tokens)
        for tone, words in TONE_WORDLISTS.items():
            matches = sum(1 for tok in tokens if tok in words)
            # emoji-style entries appear as substrings, not whitespace tokens
            matches += sum(text.count(w) for w in words if not w.isascii())
            accum[tone] += matches / total
    if counted == 0:
        return per_tone_means
    raw = {t: accum[t] / counted for t in TONE_WORDLISTS}
    total = sum(raw.values())
    if total == 0:
        return per_tone_means
    return {t: round(v / total, 4) for t, v in raw.items()}


def _from_tgstat(tgstat_data: dict | None) -> tuple[list | None, list | None]:
    """Pull audience geo + growth curve from TGStat data if present."""
    if not tgstat_data:
        return None, None
    geo = tgstat_data.get("audience_geo")
    audience_geo_top3 = geo[:3] if isinstance(geo, list) else None
    history = tgstat_data.get("subscriber_history")
    growth_curve = None
    if isinstance(history, list) and history:
        growth_curve = [
            {"date": h.get("month"), "subs": h.get("count")} for h in history
        ]
    return audience_geo_top3, growth_curve


# ── Topic mining (specific recurring themes from the channel's own posts) ────
_TOPIC_STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "this", "that", "are", "was",
    "from", "have", "has", "will", "all", "our", "out", "now", "get", "new",
    "today", "here", "more", "best", "top", "use", "how", "why", "what", "when",
    "https", "http", "www", "com", "channel", "telegram", "join", "click", "link",
    "off", "via", "they", "their", "them", "can", "but", "not", "just",
}


def _looks_like_word(tok: str) -> bool:
    """Reject abbreviation/code tokens (no vowel) like 'grbn', 'fktr', 'xyz'."""
    return any(c in "aeiou" for c in tok)


def extract_top_topics(posts: list[dict], category: str | None = None, sub_category: str | None = None, n: int = 6) -> list[str]:
    """Mine specific recurring topics (keywords + bigrams) from post text.

    Gives the Strategy/Content agents concrete topics (e.g. "amazon deals",
    "fashion coupons") instead of the broad category label.
    """
    exclude = {w for w in (category, sub_category) if w} | _TOPIC_STOPWORDS
    uni: dict[str, int] = defaultdict(int)
    bi: dict[str, int] = defaultdict(int)
    for p in posts:
        words = [
            w for w in re.findall(r"[a-z][a-z]+", (p.get("text") or "").lower())
            if len(w) >= 4 and w not in _TOPIC_STOPWORDS and _looks_like_word(w)
        ]
        for w in words:
            if w not in exclude:
                uni[w] += 1
        for a, b in zip(words, words[1:]):
            if a not in exclude or b not in exclude:
                bi[f"{a} {b}"] += 1

    # bigrams are weighted higher (more specific); keep ones seen >= 2 times
    scored = {**{w: c for w, c in uni.items()}, **{ph: c * 2 for ph, c in bi.items() if c >= 2}}
    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    out: list[str] = []
    for term, _ in ranked:
        # drop a unigram already covered by a chosen bigram
        if any(term in chosen and term != chosen for chosen in out):
            continue
        out.append(term)
        if len(out) >= n:
            break
    return out


# ── Core computation ─────────────────────────────────────────────────────────
def _select_sample_posts(window: list[dict], n: int = 5) -> list[dict] | None:
    """Pick the channel's most-engaged real text posts as style exemplars.

    Returns [{text, format}] so the content generator can mirror the channel's
    actual voice, length, emoji use and structure instead of inventing a style."""
    cand = [p for p in window if (p.get("text") or "").strip()]
    cand.sort(key=lambda p: (p.get("views") or 0) + (p.get("reactions") or 0) * 5
              + (p.get("forwards") or 0) * 5, reverse=True)
    out: list[dict] = []
    seen: set[str] = set()
    for p in cand:
        txt = " ".join((p.get("text") or "").split())
        key = txt[:60].lower()
        if len(txt) < 15 or key in seen:
            continue
        seen.add(key)
        out.append({"text": txt[:320], "format": p.get("format") or "text"})
        if len(out) >= n:
            break
    return out or None


def compute_channel_dna(
    posts: list[dict],
    member_count: int | None,
    tgstat_data: dict | None = None,
    category: str | None = None,
    sub_category: str | None = None,
    username: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run all rule-based DNA calculations. Returns a dna_payload dict.

    `posts` items need: text, format, views, forwards, reactions, replies, posted_at.
    No external I/O — safe to unit test.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=DNA_WINDOW_DAYS)

    window = [p for p in posts if p.get("posted_at") and p["posted_at"] >= cutoff]
    if not window:  # channel younger than the window — use everything
        window = list(posts)

    payload: dict[str, Any] = {
        "subscriber_count": member_count,
        "avg_views_per_post": None,
        "avg_er": None,
        "post_frequency_per_day": None,
        "best_post_hour": None,
        "best_post_days": None,
        "top_content_formats": None,
        "top_topics": None,
        "sample_posts": None,
        "tone_fingerprint": None,
        "audience_geo_top3": None,
        "growth_curve": None,
        "category": category,
        "sub_category": sub_category,
        "insufficient_data": False,
        "analysed_at": now,
    }

    audience_geo_top3, growth_curve = _from_tgstat(tgstat_data)
    payload["audience_geo_top3"] = audience_geo_top3
    payload["growth_curve"] = growth_curve

    if category is None:
        cat, sub = get_channel_category(window, username)
        payload["category"] = cat
        payload["sub_category"] = sub_category or sub
    # prefer TGStat category if our keyword pass found nothing
    if payload["category"] is None and tgstat_data and tgstat_data.get("category"):
        payload["category"] = tgstat_data["category"]

    # Capture a few REAL posts as style examples for the content generator.
    payload["sample_posts"] = _select_sample_posts(window)

    if len(window) < MIN_POSTS_FOR_DNA:
        payload["insufficient_data"] = True
        return payload

    # avg views
    views_vals = [p.get("views") or 0 for p in window]
    payload["avg_views_per_post"] = round(sum(views_vals) / len(views_vals), 2)

    # ER per post + channel avg (skip posts with no views)
    er_by_hour: dict[int, list[float]] = defaultdict(list)
    er_by_day: dict[str, list[float]] = defaultdict(list)
    er_vals: list[float] = []
    for p in window:
        er = _er_post(p, member_count)
        if er is None:
            continue
        er_vals.append(er)
        dt = p["posted_at"]
        er_by_hour[dt.hour].append(er)
        er_by_day[WEEKDAYS[dt.weekday()]].append(er)
    payload["avg_er"] = round(sum(er_vals) / len(er_vals), 3) if er_vals else None

    # post frequency over actual span (cap at window length)
    dates = [p["posted_at"] for p in window if p.get("posted_at")]
    if dates:
        span_days = max((max(dates) - min(dates)).days, 1)
        span_days = min(span_days, DNA_WINDOW_DAYS)
        payload["post_frequency_per_day"] = round(len(window) / span_days, 2)

    # best hour: argmax avg ER, only hours with >=3 posts (formulae.md §1.3)
    hour_avgs = {
        h: sum(v) / len(v) for h, v in er_by_hour.items() if len(v) >= 3
    }
    if not hour_avgs and er_by_hour:  # relax if no hour reaches 3 posts
        hour_avgs = {h: sum(v) / len(v) for h, v in er_by_hour.items()}
    if hour_avgs:
        payload["best_post_hour"] = max(hour_avgs, key=hour_avgs.get)

    # best 3 days by avg ER (formulae.md §1.4)
    day_avgs = {d: sum(v) / len(v) for d, v in er_by_day.items()}
    if day_avgs:
        payload["best_post_days"] = [
            d for d, _ in sorted(day_avgs.items(), key=lambda kv: kv[1], reverse=True)[:3]
        ]

    # format share, top 3 (formulae.md §1.5)
    fmt_count: dict[str, int] = defaultdict(int)
    for p in window:
        fmt_count[p.get("format") or "text"] += 1
    total = len(window)
    payload["top_content_formats"] = [
        {"format": f, "share": round(c / total, 3)}
        for f, c in sorted(fmt_count.items(), key=lambda kv: kv[1], reverse=True)[:3]
    ]

    # tone fingerprint (formulae.md §1.6)
    payload["tone_fingerprint"] = _tone_fingerprint(window)

    # specific recurring topics (drives strategy + content)
    payload["top_topics"] = extract_top_topics(
        window, payload.get("category"), payload.get("sub_category")
    )

    return payload


# ── TGStat (supplementary, optional) ─────────────────────────────────────────
async def get_tgstat_channel_stats(username: str) -> dict[str, Any]:
    """Fetch supplementary stats from TGStat. Returns {} on any failure/no key."""
    if not settings.TGSTAT_API_KEY:
        return {}
    username = username.lstrip("@")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.tgstat.ru/channels/stat",
                params={"token": settings.TGSTAT_API_KEY, "channelId": f"@{username}"},
            )
            resp.raise_for_status()
            data = resp.json().get("response", {})
        return {
            "subscriber_history": data.get("subscribers_growth"),
            "audience_geo": data.get("countries"),
            "category": (data.get("category") or {}).get("name") if isinstance(data.get("category"), dict) else data.get("category"),
            "avg_er_category_benchmark": data.get("err_percent"),
        }
    except Exception:
        return {}  # supplementary only — never block the agent


# ── LLM category classification (fallback when keywords find nothing) ────────
async def llm_classify_category(posts: list[dict], username: str | None = None) -> tuple[str | None, str | None]:
    """Classify a channel into one of the known categories via the LLM.

    Used when the keyword pass is inconclusive (e.g. an "entertainment" channel
    whose posts don't literally contain the narrow keyword list). Returns
    (category, sub_category) constrained to CATEGORY_KEYWORDS keys, or (None, None)
    on any failure so the caller keeps whatever it already had.
    """
    import json as _json

    from tools.llm import chat_complete

    sample = [(p.get("text") or "").replace("\n", " ").strip() for p in posts if p.get("text")]
    sample = [s for s in sample if s][:40]
    if len(sample) < 3:
        return None, None
    corpus = "\n".join(f"- {s[:200]}" for s in sample)
    allowed = ", ".join(CATEGORY_KEYWORDS.keys())
    system = (
        "You classify a Telegram channel into ONE primary content category. "
        f"Choose ONLY from this exact list: {allowed}. "
        'Reply ONLY as JSON: {"category": "<one>", "sub_category": "<one or null>"}. '
        "No prose. Pick the single best primary category; sub_category is optional."
    )
    user = f"Channel: {username or '(unknown)'}\n\nRecent posts:\n{corpus}\n\nJSON:"
    try:
        raw = await chat_complete(system, user, max_tokens=60, temperature=0.0)
    except Exception:
        return None, None
    text = raw.strip()
    if "{" in text and "}" in text:
        text = text[text.find("{"): text.rfind("}") + 1]
    try:
        data = _json.loads(text)
    except Exception:
        return None, None
    cat = str(data.get("category") or "").strip().lower() or None
    sub = str(data.get("sub_category") or "").strip().lower() or None
    if cat not in CATEGORY_KEYWORDS:
        cat = None
    if sub not in CATEGORY_KEYWORDS:
        sub = None
    return cat, sub


# ── LLM topic extraction (accurate, human-readable) ──────────────────────────
async def llm_extract_topics(posts: list[dict], category: str | None, n: int = 6) -> list[str]:
    """Extract clean, specific topic phrases from posts via the LLM.

    More accurate than rule-based mining (handles abbreviations/slang). Returns
    [] on any failure so the caller can fall back to extract_top_topics.
    """
    import json as _json

    from tools.llm import chat_complete

    sample = [(p.get("text") or "").replace("\n", " ").strip() for p in posts if p.get("text")]
    sample = [s for s in sample if s][:40]
    if len(sample) < 3:
        return []
    corpus = "\n".join(f"- {s[:200]}" for s in sample)
    system = (
        "You analyse a Telegram channel's posts and name its main recurring content "
        "topics. Expand abbreviations/slang into real words. Return ONLY a JSON array "
        f"of {n} short, specific topic phrases (2-3 words each), most frequent first. "
        "No generic words like 'deals' alone — be concrete (e.g. 'Amazon electronics deals')."
    )
    user = f"Category: {category}\n\nPosts:\n{corpus}\n\nJSON array of topics:"
    try:
        raw = await chat_complete(system, user, max_tokens=200, temperature=0.2)
    except Exception:
        return []
    text = raw.strip()
    if "[" in text and "]" in text:
        text = text[text.find("["): text.rfind("]") + 1]
    try:
        data = _json.loads(text)
        return [str(t).strip() for t in data if str(t).strip()][:n] if isinstance(data, list) else []
    except Exception:
        return []


# ── Persistence ──────────────────────────────────────────────────────────────
_DNA_COLUMNS = {
    "subscriber_count", "avg_views_per_post", "avg_er", "post_frequency_per_day",
    "best_post_hour", "best_post_days", "top_content_formats", "top_topics",
    "sample_posts", "tone_fingerprint", "audience_geo_top3", "growth_curve", "category",
    "sub_category", "insufficient_data", "analysed_at",
}


async def save_channel_dna(channel_id: str | uuid.UUID, dna_payload: dict) -> dict[str, Any]:
    """Upsert the channel_dna row for a channel. Sets analysed_at to now if absent."""
    cid = uuid.UUID(str(channel_id))
    fields = {k: v for k, v in dna_payload.items() if k in _DNA_COLUMNS}
    fields.setdefault("analysed_at", datetime.now(timezone.utc))
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(ChannelDNA).where(ChannelDNA.channel_id == cid))
        ).scalar_one_or_none()
        if existing is None:
            row = ChannelDNA(channel_id=cid, **fields)
            session.add(row)
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
            row = existing
        await session.commit()
        await session.refresh(row)
        return {"success": True, "record_id": str(row.id)}
