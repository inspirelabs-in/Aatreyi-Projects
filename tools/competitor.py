"""Competitor Intelligence tools (Phase 3).

Discovery (DuckDuckGo -> Telegram search -> TGStat -> Telemetr), metric
computation, the weighted ranking formula (formulae.md §2), dedup, and
persistence. Pure functions (rank/dedup/metrics/extraction) are unit-testable
without any network.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select

from config import settings
from db.base import AsyncSessionLocal
from db.models import Competitor, CompetitorPost, DiscoverySource
from tools.channel_dna import CATEGORY_KEYWORDS, _CATEGORY_PATTERNS
from tools.llm import chat_complete

# Ranking weights — topic/content similarity first, then engagement signals
W_TOPIC_SIM   = 0.50  # Jaccard overlap of channel topics
W_CONTENT_SIM = 0.20  # LLM-rated content focus similarity
W_ER_SIM      = 0.15  # engagement rate similarity
W_FREQ_SIM    = 0.10  # posting frequency similarity
W_SUBS_SIM    = 0.05  # subscriber count similarity
DISAPPEARING_PENALTY = 0.7
COMPETITOR_WINDOW_DAYS = 30

# Candidates whose topic_similarity falls below this are rejected before ranking.
# Only applied when the managed channel has known topics; avoids false rejections
# for channels with no DNA yet.
TOPIC_SIM_THRESHOLD = 0.30

# Categories where competitors are AGGREGATOR platforms, not the retailers/brands
# those platforms feature. Discovery uses keyword search + explicit LLM framing.
_AGGREGATOR_CATEGORIES = {"deals", "shopping", "coupons", "offers"}

# Per-category Telegram search queries used to find competitor channels directly
# by what they post about — bypasses brand-name guessing entirely.
CATEGORY_SEARCH_KEYWORDS: dict[str, list[str]] = {
    "deals":         ["deals india", "coupon india", "cashback india", "offer alert india", "discount india"],
    "shopping":      ["shopping deals india", "online shopping offers india", "best deals india"],
    "coupons":       ["coupon code india", "promo code india", "discount code india"],
    "offers":        ["offers india", "best offers india", "cashback offers india"],
    "tech":          ["tech news india", "gadgets india", "technology india"],
    "crypto":        ["crypto india", "cryptocurrency india", "bitcoin india", "web3 india"],
    "finance":       ["personal finance india", "investing india", "stock market india"],
    "news":          ["india news", "breaking news india", "daily news india"],
    "entertainment": ["entertainment india", "bollywood updates", "movies india"],
    "gaming":        ["gaming india", "mobile gaming india", "esports india"],
    "education":     ["online learning india", "education india", "courses india"],
    "health":        ["health india", "fitness india", "wellness india"],
    "business":      ["business india", "startup india", "entrepreneurship india"],
    "sports":        ["sports india", "cricket india", "ipl updates"],
}

# ── Competitor qualification benchmarks ──────────────────────────────────────
# A real competitor must be an established, active channel of comparable scale —
# not a tiny or dormant channel that happens to match a keyword.
MIN_COMPETITOR_MEMBERS = 10_000        # absolute floor: must be an established channel
MIN_COMPETITOR_POSTS = 3               # must be active (>= N recent posts in the window)
MIN_PEER_SUBSCRIBER_RATIO = 0.05       # peer scale: >= 5% of the managed channel's size
MIN_QUALIFIED_COMPETITORS = 3          # below this, relax the peer-ratio so we never zero out


def qualifies_as_competitor(
    members: int | None, post_count: int, metrics: dict, my_subscribers: int | None = 0
) -> tuple[bool, str]:
    """Gate a candidate against competitor benchmarks. Returns (ok, reason).

    Rejects channels that are too small (absolute or relative to us), dormant
    (no recent posts), or with no measurable engagement — so the benchmark set
    reflects genuine, comparable rivals rather than keyword-matched noise.
    """
    members = members or 0
    if members < MIN_COMPETITOR_MEMBERS:
        return False, f"too small ({members} < {MIN_COMPETITOR_MEMBERS} subscribers)"
    floor = int((my_subscribers or 0) * MIN_PEER_SUBSCRIBER_RATIO)
    if floor and members < floor:
        return False, f"not a peer ({members} < {floor}, i.e. <{int(MIN_PEER_SUBSCRIBER_RATIO*100)}% of your size)"
    if post_count < MIN_COMPETITOR_POSTS:
        return False, f"inactive ({post_count} recent posts < {MIN_COMPETITOR_POSTS})"
    if not metrics.get("post_frequency_per_day"):
        return False, "no measurable posting activity"
    if metrics.get("avg_er") is None:
        return False, "no measurable engagement"
    return True, "qualified"

_USERNAME_RE = re.compile(r"(?:t\.me/|telegram\.me/|@)([A-Za-z][A-Za-z0-9_]{3,31})", re.I)
# usernames that appear in t.me links but are not channels
_USERNAME_BLOCKLIST = {"share", "joinchat", "addstickers", "proxy", "s", "iv", "telegram"}


# ── Username extraction (pure) ───────────────────────────────────────────────
def extract_telegram_usernames(*texts: str) -> list[str]:
    """Pull telegram channel usernames from text/URLs (t.me/... or @mentions)."""
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for m in _USERNAME_RE.finditer(text or ""):
            uname = m.group(1).lower()
            if uname in _USERNAME_BLOCKLIST or uname in seen:
                continue
            seen.add(uname)
            found.append(uname)
    return found


# ── Jaccard / relevance (pure) ───────────────────────────────────────────────
def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def extract_channel_topics(posts: list[dict], n: int = 10) -> list[str]:
    """Extract the top recurring topics from a set of posts (reuses DNA logic)."""
    from tools.channel_dna import extract_top_topics
    return extract_top_topics(posts, n=n)


def compute_topic_similarity(my_topics: list[str], candidate_topics: list[str]) -> float:
    """Jaccard similarity between two topic lists."""
    a = {t.lower().strip() for t in my_topics if t}
    b = {t.lower().strip() for t in candidate_topics if t}
    return round(_jaccard(a, b), 3)


async def compute_content_similarity(my_topics: list[str], candidate_topics: list[str]) -> float:
    """LLM rates content-focus overlap 0-100, returned as 0.0-1.0.

    Fast call (max_tokens=10, temperature=0) — just a single integer back.
    Falls back to 0.0 on any error so it never blocks the pipeline.
    """
    if not my_topics or not candidate_topics:
        return 0.0
    system = "You rate topic similarity between two Telegram channels. Reply with ONLY a single integer 0-100. No other text."
    user = (
        f"Channel A: {', '.join(my_topics[:8])}\n"
        f"Channel B: {', '.join(candidate_topics[:8])}\n\n"
        "How similar is their content focus? (0=completely different, 100=identical)"
    )
    try:
        raw = await chat_complete(system, user, max_tokens=10, temperature=0.0)
        score = float("".join(c for c in raw.strip() if c.isdigit() or c == "."))
        return round(min(max(score, 0.0), 100.0) / 100.0, 3)
    except Exception:
        return 0.0


def channel_keyword_set(category: str | None, sub_category: str | None, topics) -> set[str]:
    kw: set[str] = set()
    for v in (category, sub_category):
        if v:
            kw.add(v.lower())
    for t in topics or []:
        if t:
            kw.add(str(t).lower())
    return kw


def extract_themes(posts: list[dict]) -> list[str]:
    """Detect category themes present in a competitor's posts (for relevance).

    Uses whole-word matching (not substring str.count) with a minimum hit floor:
    a single incidental mention of "ai"/"money"/"health" must not tag a deals
    competitor as tech/finance/health — which then surfaced as bogus "content
    gaps" ("how can a deals channel post about tech?"). A theme only counts when
    the keyword appears >=2 times as a standalone word."""
    corpus = " ".join((p.get("text") or "") for p in posts).lower()
    hits = {
        cat: sum(len(pat.findall(corpus)) for pat in pats)
        for cat, pats in _CATEGORY_PATTERNS.items()
    }
    return [cat for cat, c in sorted(hits.items(), key=lambda kv: kv[1], reverse=True) if c >= 2][:5]


# ── Competitor metrics (pure; formulae.md §6 ER) ─────────────────────────────
def competitor_post_er(post: dict) -> float:
    """ER for a competitor post = (reactions + forwards) / max(views,1) * 100."""
    views = post.get("views") or 0
    eng = (post.get("reactions") or post.get("reactions_count") or 0) + (post.get("forwards") or 0)
    return eng / max(views, 1) * 100.0


def compute_competitor_metrics(posts: list[dict], member_count: int | None) -> dict[str, Any]:
    """avg ER, posting frequency, and themes for a competitor candidate."""
    if not posts:
        return {"avg_er": None, "post_frequency_per_day": None, "top_themes": []}
    ers = [competitor_post_er(p) for p in posts]
    avg_er = round(sum(ers) / len(ers), 3)
    dates = [p["posted_at"] for p in posts if p.get("posted_at")]
    if dates:
        span = min(max((max(dates) - min(dates)).days, 1), COMPETITOR_WINDOW_DAYS)
        freq = round(len(posts) / span, 2)
    else:
        freq = None
    return {"avg_er": avg_er, "post_frequency_per_day": freq, "top_themes": extract_themes(posts)}


# ── Dedup (pure) ─────────────────────────────────────────────────────────────
def dedup_competitor_list(
    candidates: list[dict], existing_usernames: set[str] | None = None, managed_username: str | None = None
) -> list[dict]:
    """Drop the managed channel, already-tracked channels, and duplicates."""
    existing = {u.lstrip("@").lower() for u in (existing_usernames or set())}
    managed = (managed_username or "").lstrip("@").lower()
    out: list[dict] = []
    seen: set[str] = set()
    for c in candidates:
        uname = (c.get("username") or "").lstrip("@").lower()
        if not uname or uname == managed or uname in existing or uname in seen:
            continue
        seen.add(uname)
        out.append(c)
    return out


# ── Ranking (pure; formulae.md §2) ───────────────────────────────────────────
def rank_competitors(candidates: list[dict], channel_keywords: set[str]) -> list[dict]:
    """Weighted composite rank using topic/content similarity as primary signals.

    Formula (formulae.md §2 — updated):
        50% topic_similarity  (Jaccard of DNA topics)
        20% content_similarity (LLM-rated focus overlap)
        15% ER similarity
        10% posting frequency similarity
         5% subscriber count similarity
    """
    if not candidates:
        return []

    def col(key):
        return [float(c.get(key) or 0) for c in candidates]

    topic_sims  = col("topic_similarity")
    content_sims = col("content_similarity")
    ers   = col("avg_er")
    freqs = col("post_frequency_per_day")
    subs  = col("subscriber_count")

    def norm(x, arr):
        lo, hi = min(arr), max(arr)
        return 0.5 if hi == lo else (x - lo) / (hi - lo)

    for c, ts, cs, e, f, s in zip(candidates, topic_sims, content_sims, ers, freqs, subs):
        score = (
            W_TOPIC_SIM   * norm(ts, topic_sims)
            + W_CONTENT_SIM * norm(cs, content_sims)
            + W_ER_SIM      * norm(e,  ers)
            + W_FREQ_SIM    * norm(f,  freqs)
            + W_SUBS_SIM    * norm(s,  subs)
        ) * 100
        if c.get("has_disappearing_messages"):
            score *= DISAPPEARING_PENALTY
        c["rank_score"] = round(score, 2)

    ranked = sorted(candidates, key=lambda c: c["rank_score"], reverse=True)
    for i, c in enumerate(ranked, 1):
        c["rank"] = i
    return ranked


# ── Brand-centric discovery (PRIMARY) ────────────────────────────────────────
_LAST_SEARCH = [0.0]
_SEARCH_MIN_INTERVAL = 1.3  # throttle bursts — free DDGS rate-limits aggressively


def _web_search(query: str, max_results: int = 10, retries: int = 2) -> list[dict]:
    """DDGS text search -> [{title, body, url}]. Throttled + retried; [] on failure."""
    try:
        from ddgs import DDGS
    except Exception:
        return []
    for attempt in range(retries + 1):
        wait = _SEARCH_MIN_INTERVAL - (time.time() - _LAST_SEARCH[0])
        if wait > 0:
            time.sleep(wait)
        _LAST_SEARCH[0] = time.time()
        out: list[dict] = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    out.append({
                        "title": r.get("title", ""),
                        "body": r.get("body", ""),
                        "url": r.get("href") or r.get("url") or "",
                    })
            if out:
                return out
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))  # back off on rate-limit/empty
    return out


def _parse_brand_list(raw: str) -> list[str]:
    """Parse an LLM reply into a list of brand names (JSON array or bullet lines)."""
    text = raw.strip()
    if "```" in text:
        for part in text.split("```"):
            if "[" in part:
                text = part[part.find("["):]
                break
    try:
        data = json.loads(text[text.find("["): text.rfind("]") + 1])
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    # fallback: split lines / commas, strip bullets and numbering
    lines = re.split(r"[\n,]", raw)
    out = []
    for ln in lines:
        ln = re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip()
        if ln and len(ln) < 60:
            out.append(ln)
    return out


async def discover_competitor_brands(
    brand: str, category: str | None, topics: list[str] | None = None, max_brands: int = 15
) -> list[str]:
    """Find the channel's REAL competitor brands via web search + LLM extraction.

    Brand-first step: identify the actual companies/brands/popular channels that
    compete with `brand` in `category` (e.g. GrabOn -> CashKaro, CouponDunia,
    DesiDime, FreeKaaMaal...), grounded in live web results, before we look for
    Telegram channels. Two complementary searches widen the candidate pool.
    """
    topic_hint = (topics or [None])[0] or ""
    topics_str = ", ".join((topics or [])[:4])
    generic = _brand_is_generic(brand, category)
    cat_key = (category or "").lower().strip()
    is_aggregator = cat_key in _AGGREGATOR_CATEGORIES

    if is_aggregator:
        # For deal/coupon categories the LLM must return AGGREGATOR platforms
        # (CashKaro, CouponDunia, DesiDime…), NOT the retailers those platforms
        # feature (Amazon, Flipkart, Nykaa). Two searches maximise recall:
        # one brand-anchored, one category-anchored.
        results = _web_search(f"top coupon cashback deal aggregator websites India alternatives to {brand}", 10)
        results += _web_search(f"best coupon code cashback saving apps websites India 2024", 10)
    elif generic:
        results = _web_search(f"best {topic_hint or category} telegram channels India".strip(), 10)
        results += _web_search(f"popular {category} channels {topics_str}".strip(), 10)
    else:
        results = _web_search(f"top competitors of {brand} {category or ''} {topic_hint} India".strip(), 10)
        results += _web_search(f"best {category or ''} apps websites and telegram channels India".strip(), 10)

    seen_ctx, context_lines = set(), []
    for r in results:
        key = r.get("url") or r.get("title")
        if key and key not in seen_ctx:
            seen_ctx.add(key)
            context_lines.append(f"- {r['title']}: {r['body']}")
    context = "\n".join(context_lines[:16]) or "(no web results)"
    system = (
        "You identify real, well-known, ESTABLISHED Indian competitors — major India-based brands "
        "and popular, actively-posting Indian Telegram channels with a substantial audience. "
        "Exclude US/UAE/non-Indian brands, tiny, obscure, inactive, or personal channels. "
        "Reply ONLY with a JSON array of brand/company/channel names (strings), most prominent first, no prose."
    )
    if is_aggregator:
        user = (
            f"Brand: {brand}\nCategory: {category}\nMarket: India\n\n"
            f"Web search context:\n{context}\n\n"
            f"List {max_brands} real, established INDIA-BASED COUPON AGGREGATOR or CASHBACK PLATFORMS "
            f"that compete directly with \"{brand}\" — Indian websites and apps that collect and "
            f"publish deals, coupons, promo codes, and cashback offers from retailers.\n\n"
            f"CRITICAL RULES:\n"
            f"- India-based platforms ONLY. Do NOT list US/UAE/global-only platforms.\n"
            f"- Do NOT list retailers (e.g. Amazon, Flipkart, Myntra, Nykaa, Meesho).\n"
            f"- Do NOT list e-commerce marketplaces.\n"
            f"- ONLY list platforms whose core product is aggregating/curating deals for India.\n"
            f"Examples of valid answers: CashKaro, CouponDunia, DesiDime, Zoutons, "
            f"FreeKaaMaal, GoPaisa, Couponzguru, MagicPin, PaisaWapas.\n"
            f"JSON array of platform names only."
        )
    elif generic:
        user = (
            f"Category: {category}\nContent focus (what this channel actually posts): {topics_str}\n"
            f"Market: India\n\n"
            f"Web search context:\n{context}\n\n"
            f"List {max_brands} real, well-known INDIAN brands, accounts, or popular Indian Telegram channels "
            f"that publish the SAME kind of content — specifically about: {topics_str}. "
            f"They must genuinely match this {category} niche (not just the broad category) and target Indian audiences. "
            f"JSON array of names only."
        )
    else:
        user = (
            f"Brand: {brand}\nCategory: {category}\nNiche topics: {', '.join(topics or [])}\nMarket: India\n\n"
            f"Web search context:\n{context}\n\n"
            f"List {max_brands} real, established INDIA-BASED competitors of \"{brand}\" in the {category} "
            f"space — well-known rival Indian apps, websites, AND popular Indian {category} Telegram channels "
            f"that are comparable or larger in scale and actively post. "
            f"Exclude non-Indian brands, \"{brand}\" itself, and any small or dormant channels. JSON array of names only."
        )
    try:
        raw = await chat_complete(system, user, max_tokens=400, temperature=0.4)
    except Exception:
        return []
    brands = _parse_brand_list(raw)
    bl = brand.lower()
    seen: set[str] = set()
    out: list[str] = []
    for b in brands:
        key = b.lower()
        if key and key != bl and key not in seen:
            seen.add(key)
            out.append(b)
    return out[:max_brands]


# Words that don't identify a real brand on their own — a channel name made up
# only of these (+ its category) has no brand to find market rivals of.
_GENERIC_BRAND_WORDS = {
    "channel", "official", "telegram", "group", "updates", "update", "daily",
    "world", "india", "indian", "hub", "zone", "tv", "media", "news", "latest",
    "the", "and", "videos", "video", "content", "online", "free", "best", "top",
    "entertainment", "deals", "tech", "crypto", "finance", "sports", "gaming",
    "education", "health", "business", "shopping", "movies", "music",
}


def _brand_is_generic(brand: str | None, category: str | None) -> bool:
    """True when the channel name carries no distinctive brand token (e.g.
    "Entertainment 🎬", "Daily Tech Updates") — only generic/category words.
    Such a name can't anchor a "competitors of <brand>" search, so discovery
    should pivot to the niche + topics instead."""
    import re as _re

    core = _re.sub(r"[^a-z0-9 ]", " ", (brand or "").lower())
    tokens = [t for t in core.split() if t]
    if not tokens:
        return True
    cat = (category or "").lower()
    return all(t == cat or t in _GENERIC_BRAND_WORDS for t in tokens)


def _brand_key(brand: str) -> str:
    core = re.sub(r"[^a-z0-9]", "", brand.lower())
    return core[:6] if len(core) >= 6 else core


def _is_spam_channel(username: str) -> bool:
    """True when a username looks like a fan/aggregator/keyword-stuffed channel.

    Real brand channels have clean, short handles.  Spam channels cram multiple
    brand names and deal keywords into long underscore-separated strings like
    @myntra_Ajio_Sale_Deals_offers_li or @amazon_flipkart_deals_2024.
    """
    u = username.lstrip("@").lower()
    if len(u) > 25:
        return True
    if u.count("_") > 3:
        return True
    # Multiple well-known brand names inside a single handle → fan/aggregator
    _RETAILER_TOKENS = {"myntra", "ajio", "flipkart", "amazon", "nykaa", "meesho",
                        "snapdeal", "paytm", "zomato", "swiggy", "zepto", "blinkit"}
    if sum(1 for t in _RETAILER_TOKENS if t in u) >= 2:
        return True
    return False


async def discover_channels_by_keywords(
    client,
    keywords: list[str],
    min_members: int = 1_000,
    limit_per_kw: int = 12,
) -> list[dict]:
    """Search Telegram directly by category keywords to find competitor channels.

    For aggregator categories (deals, coupons, etc.) this is the PRIMARY discovery
    path — it finds real peers by what they *post about*, not by guessing company
    names from web-search results.  Brand-name resolution supplements this.

    Returns candidates sorted by subscriber count descending (highest-signal
    channels first), deduped by username, spam-filtered.
    """
    found: dict[str, dict] = {}  # username -> channel info
    for kw in keywords:
        try:
            res = await search_telegram_channels(client, kw, limit=limit_per_kw)
            for c in res["channels"]:
                uname = (c.get("username") or "").lower()
                if not uname or _is_spam_channel(uname):
                    continue
                members = c.get("member_count") or 0
                if members < min_members:
                    continue
                # keep the record with the highest member count for dedup
                if uname not in found or (found[uname].get("member_count") or 0) < members:
                    found[uname] = c
        except Exception:
            pass
    return sorted(found.values(), key=lambda c: c.get("member_count") or 0, reverse=True)


async def find_brand_telegram_channels(brand: str, client=None, max_per: int = 3) -> list[str]:
    """Find a brand's Telegram channel(s).

    Strategy (in priority order):
    1. Telegram native SearchRequest — searches Telegram's own channel index,
       most reliable for established brands (CouponDunia, DesiDime, Zoutons…).
    2. Web search for t.me links — supplementary, fills gaps when Telegram
       search doesn't surface the handle by that keyword.

    A handle is accepted if the brand key (first 6 alphanum chars) appears in the
    handle OR title, OR if the first 4 chars of the brand name appear in the title
    (catches 'DesiDime Official' matching 'desi…' etc.)
    """
    key = _brand_key(brand)
    brand_clean = re.sub(r"[^a-z0-9]", "", brand.lower())
    brand4 = brand_clean[:4]
    if not key or not brand4:
        return []

    found: list[str] = []
    seen: set[str] = set()

    def _add(u: str) -> None:
        u = u.lstrip("@").lower()
        if u and len(u) >= 4 and u not in seen:
            seen.add(u)
            found.append(u)

    # 1. Telegram native search — single query is enough for established brands.
    if client is not None:
        try:
            res = await search_telegram_channels(client, brand, limit=10)
            for c in res["channels"]:
                uname = (c.get("username") or "").lower()
                title = (c.get("title") or "").lower()
                if not uname or _is_spam_channel(uname):
                    continue
                if (key in uname or brand4 in uname or
                        (len(brand4) >= 4 and brand4 in title)):
                    _add(uname)
        except Exception:
            pass

    # 2. Web search for t.me links (fallback / no Telegram client)
    strong: list[str] = []
    weak: list[str] = []
    for r in _web_search(f"{brand} official telegram channel t.me", max_results=8):
        text = f"{r['title']} {r['body']}".lower()
        for u in extract_telegram_usernames(f"{r['title']} {r['body']} {r['url']}"):
            ul = u.lower()
            if key in ul and u not in strong:
                strong.append(u)
            elif (key in text or brand4 in text) and u not in weak:
                weak.append(u)
    for u in strong + weak:
        _add(u)

    # 3. Public-web verification (t.me/s), ALWAYS run (httpx-only, fast). It loads
    #    the channel's public preview to CONFIRM a real handle that matches the
    #    brand — reliable even when the Telethon session is down or in-app search
    #    returns weak/no matches. The verified handle is trusted, so it goes FIRST
    #    (a weak Telegram guess can't shadow the confirmed channel).
    web_handle: str | None = None
    try:
        from tools.telegram_web import resolve_brand_handle
        data = await resolve_brand_handle(brand)
        if data and data.get("username"):
            web_handle = data["username"].lstrip("@").lower()
    except Exception:
        pass

    ordered = ([web_handle] if web_handle else []) + [u for u in found if u != web_handle]
    return [f"@{u}" for u in ordered[:max_per]]


# ── Benchmarks (pure) — what Strategy targets against ────────────────────────
def compute_benchmarks(competitors: list[dict], my_dna: dict | None = None) -> dict[str, Any]:
    """Competitor benchmark stats + the managed channel's gap vs them."""
    def avg(key):
        xs = [c[key] for c in competitors if c.get(key) is not None]
        return round(sum(xs) / len(xs), 3) if xs else None

    bench_er = avg("avg_er")
    my_er = (my_dna or {}).get("avg_er")
    top = max(competitors, key=lambda c: c.get("rank_score") or 0, default=None)
    # union of competitor themes the channel can target
    themes: set[str] = set()
    for c in competitors:
        for t in (c.get("top_themes") or c.get("top_content_themes") or []):
            themes.add(str(t).lower())
    return {
        "competitor_count": len(competitors),
        "competitor_avg_subscribers": avg("subscriber_count"),
        "competitor_avg_er": bench_er,
        "competitor_avg_frequency": avg("post_frequency_per_day"),
        "my_avg_er": my_er,
        "er_gap": (round(bench_er - my_er, 3) if bench_er is not None and my_er is not None else None),
        "top_competitor": top.get("username") if top else None,
        "competitor_themes": sorted(themes),
    }


# ── Discovery: DuckDuckGo channel-link search (FALLBACK) ──────────────────────
def search_competitors_duckduckgo(query: str, max_results: int = 20) -> dict[str, Any]:
    """Web search via DDGS; extract telegram usernames from titles/snippets/urls."""
    try:
        from ddgs import DDGS
    except Exception:
        return {"usernames": [], "source_urls": []}
    usernames: list[str] = []
    urls: list[str] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                blob = " ".join(
                    str(r.get(k, "")) for k in ("title", "body", "href", "url")
                )
                usernames += extract_telegram_usernames(blob)
                if r.get("href") or r.get("url"):
                    urls.append(r.get("href") or r.get("url"))
    except Exception:
        pass
    # dedup usernames, preserve order
    seen: set[str] = set()
    uniq = [u for u in usernames if not (u in seen or seen.add(u))]
    return {"usernames": uniq, "source_urls": urls}


# ── Discovery: Telegram native recommendations (PRIMARY, most reliable) ──────
async def get_telegram_recommended_channels(client, username: str, limit: int = 20) -> dict[str, Any]:
    """Telegram's OWN 'similar channels' recommender (GetChannelRecommendations).

    The most reliable competitor source: real channels with real member counts,
    algorithmically similar — no web-search handle guessing. Empty for some
    channels (Telegram has no recommendations), so callers fall back.
    """
    from telethon.tl.functions.channels import GetChannelRecommendationsRequest

    out: list[dict] = []
    try:
        ent = await client.get_entity(username)
        res = await client(GetChannelRecommendationsRequest(channel=ent))
    except Exception:
        return {"channels": out}
    for c in getattr(res, "chats", [])[:limit]:
        u = getattr(c, "username", None)
        if u:
            out.append({
                "username": u,
                "display_name": getattr(c, "title", None),
                "subscriber_count": getattr(c, "participants_count", None),
            })
    return {"channels": out}


# ── Discovery: Telegram public search (network, Telethon) ────────────────────
async def search_telegram_channels(client, keyword: str, limit: int = 10) -> dict[str, Any]:
    """SearchPublicRequest via Telethon -> channel usernames + member counts."""
    import asyncio as _asyncio
    from telethon.errors import FloodWaitError
    from telethon.tl.functions.contacts import SearchRequest
    from telethon.tl.types import Channel as TLChannel

    try:
        res = await client(SearchRequest(q=keyword, limit=limit))
    except FloodWaitError as e:
        await _asyncio.sleep(min(e.seconds + 2, 60))
        try:
            res = await client(SearchRequest(q=keyword, limit=limit))
        except Exception:
            return {"channels": []}
    except Exception:
        return {"channels": []}
    channels = []
    for chat in getattr(res, "chats", []):
        if isinstance(chat, TLChannel) and getattr(chat, "username", None) and getattr(chat, "broadcast", False):
            channels.append(
                {
                    "username": chat.username,
                    "title": getattr(chat, "title", None),
                    "member_count": getattr(chat, "participants_count", None),
                }
            )
    return {"channels": channels}


# ── Discovery fallbacks: TGStat / Telemetr (network) ─────────────────────────
async def get_tgstat_similar_channels(username: str, limit: int = 15) -> dict[str, Any]:
    if not settings.TGSTAT_API_KEY:
        return {"channels": []}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://api.tgstat.ru/channels/similar",
                params={"token": settings.TGSTAT_API_KEY, "channelId": f"@{username.lstrip('@')}", "limit": limit},
            )
            r.raise_for_status()
            data = r.json().get("response", []) or []
        return {
            "channels": [
                {"username": d.get("username"), "member_count": d.get("participants_count"), "category": d.get("category")}
                for d in data if d.get("username")
            ]
        }
    except Exception:
        return {"channels": []}


async def get_telemetr_similar_channels(username: str, limit: int = 15) -> dict[str, Any]:
    if not settings.TELEMETR_API_KEY:
        return {"channels": []}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://api.telemetr.io/v1/channels/similar",
                params={"username": username.lstrip("@"), "limit": limit},
                headers={"x-api-key": settings.TELEMETR_API_KEY},
            )
            r.raise_for_status()
            data = r.json().get("data", []) or []
        return {
            "channels": [
                {"username": d.get("username"), "member_count": d.get("members"), "er": d.get("er")}
                for d in data if d.get("username")
            ]
        }
    except Exception:
        return {"channels": []}


# ── Top posts (network, reuses shared get_channel_posts) ─────────────────────
async def get_competitor_top_posts(client, channel: str, limit: int = 10, days: int = 30) -> dict[str, Any]:
    from tools.shared import get_channel_posts

    posts = (await get_channel_posts(client, channel, days=days, limit=200))["posts"]
    posts.sort(key=lambda p: p.get("views") or 0, reverse=True)
    top = posts[:limit]
    for p in top:
        p["er"] = round(competitor_post_er(p), 3)
        p["text_preview"] = (p.get("text") or "")[:500]
    return {"posts": top}


# ── Persistence ──────────────────────────────────────────────────────────────
async def get_tracked_usernames(channel_id: str | uuid.UUID) -> set[str]:
    """Usernames already stored as competitors for this channel (for dedup)."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Competitor.competitor_username).where(Competitor.channel_id == cid)
            )
        ).scalars().all()
    return {u.lstrip("@").lower() for u in rows}


async def save_competitors(channel_id: str | uuid.UUID, competitors: list[dict]) -> dict[str, Any]:
    """Upsert competitors (dedup by channel_id+username) + replace their top posts."""
    cid = uuid.UUID(str(channel_id))
    upserted = skipped = 0
    async with AsyncSessionLocal() as session:
        for c in competitors:
            uname = (c.get("username") or "").lstrip("@")
            if not uname:
                skipped += 1
                continue
            row = (
                await session.execute(
                    select(Competitor).where(
                        Competitor.channel_id == cid, Competitor.competitor_username == uname
                    )
                )
            ).scalar_one_or_none()
            src = c.get("source")
            fields = dict(
                competitor_tg_id=c.get("competitor_tg_id"),
                display_name=c.get("display_name"),
                subscriber_count=c.get("subscriber_count"),
                post_frequency_per_day=c.get("post_frequency_per_day"),
                avg_er=c.get("avg_er"),
                top_content_themes=c.get("top_themes"),
                source=DiscoverySource(src) if src in DiscoverySource.__members__ else None,
                rank=c.get("rank"),
                rank_score=c.get("rank_score"),
                topic_similarity=c.get("topic_similarity"),
                content_similarity=c.get("content_similarity"),
                competitor_type=c.get("competitor_type"),
                similarity_breakdown=c.get("similarity_breakdown"),
                intelligence=c.get("intelligence"),
                has_disappearing_messages=bool(c.get("has_disappearing_messages")),
                refreshed_at=datetime.now(timezone.utc),
            )
            if row is None:
                row = Competitor(channel_id=cid, competitor_username=uname, **fields)
                session.add(row)
                await session.flush()
            else:
                for k, v in fields.items():
                    setattr(row, k, v)
                # clear old posts before re-inserting (explicit delete; no lazy load)
                await session.execute(
                    delete(CompetitorPost).where(CompetitorPost.competitor_id == row.id)
                )
            for p in c.get("posts", []) or []:
                session.add(
                    CompetitorPost(
                        competitor_id=row.id,
                        telegram_message_id=p.get("message_id"),
                        text_preview=p.get("text_preview") or (p.get("text") or "")[:500],
                        format=p.get("format") if p.get("format") in {"text", "photo", "video", "poll", "link"} else None,
                        views=p.get("views"),
                        forwards=p.get("forwards"),
                        reactions_count=p.get("reactions") or p.get("reactions_count"),
                        er=p.get("er"),
                        posted_at=p.get("posted_at"),
                    )
                )
            upserted += 1
        await session.commit()
    return {"upserted": upserted, "skipped": skipped}


async def prune_stale_competitors(
    channel_id: str | uuid.UUID, run_started_at: datetime
) -> dict[str, Any]:
    """Delete competitors not (re)discovered in the latest run.

    save_competitors stamps `refreshed_at` on every row it upserts this run, so
    rows still carrying an OLDER timestamp are leftovers from a previous, possibly
    mis-categorised discovery (e.g. tech channels saved before the channel was
    correctly classified as entertainment). Removing them gives the re-run true
    replace-semantics. Caller should gate this on a healthy yield so a throttled,
    low-yield run doesn't wipe a good set. Returns count removed + kept.
    """
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Competitor).where(Competitor.channel_id == cid))).scalars().all()
        removed = []
        for r in rows:
            if r.refreshed_at is None or r.refreshed_at < run_started_at:
                removed.append(r.competitor_username)
                await session.delete(r)
        await session.commit()
        survivors = (
            await session.execute(
                select(Competitor).where(Competitor.channel_id == cid)
                .order_by(Competitor.rank_score.desc().nulls_last())
            )
        ).scalars().all()
        for i, r in enumerate(survivors, 1):
            r.rank = i
        await session.commit()
        return {"removed": len(removed), "removed_usernames": removed, "kept": len(survivors)}


async def prune_unqualified_competitors(
    channel_id: str | uuid.UUID, min_subs: int = MIN_COMPETITOR_MEMBERS
) -> dict[str, Any]:
    """Delete saved competitors that no longer meet the size benchmark (e.g. junk
    from older runs before qualification existed). Keeps the set accurate even
    when a fresh discovery run finds nothing new. Returns count removed + kept."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Competitor).where(Competitor.channel_id == cid))).scalars().all()
        removed = []
        for r in rows:
            # prune only channels we have a real count for that's below the floor
            # (junk channels). Market-only competitors (no Telegram channel -> null
            # count) are kept — they're real business rivals, not junk.
            if r.subscriber_count is not None and r.subscriber_count < min_subs:
                removed.append(r.competitor_username)
                await session.delete(r)
        await session.commit()
        # re-rank the survivors so ranks stay contiguous (1..n by rank_score)
        survivors = (
            await session.execute(
                select(Competitor).where(Competitor.channel_id == cid)
                .order_by(Competitor.rank_score.desc().nulls_last())
            )
        ).scalars().all()
        for i, r in enumerate(survivors, 1):
            r.rank = i
        await session.commit()
        return {"removed": len(removed), "removed_usernames": removed, "kept": len(survivors)}


# ── Daily competitor post refresh ─────────────────────────────────────────────
async def refresh_competitor_posts_for_channel(
    channel_id: str | uuid.UUID, client, days: int = 2
) -> dict[str, Any]:
    """Fetch the latest posts from all on-Telegram competitors and update the DB.

    Called daily so strategy always sees what competitors are posting TODAY —
    not just what they posted during the last weekly run. Adds new posts by
    telegram_message_id (dedup), recomputes avg_er on the competitor row.
    """
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Competitor).where(
                    Competitor.channel_id == cid,
                    Competitor.subscriber_count.isnot(None),
                )
            )
        ).scalars().all()

    updated = 0
    for comp in rows:
        try:
            posts = (await get_competitor_top_posts(client, comp.competitor_username, days=days))["posts"]
        except Exception:
            continue
        async with AsyncSessionLocal() as session:
            existing_ids = set(
                (
                    await session.execute(
                        select(CompetitorPost.telegram_message_id).where(
                            CompetitorPost.competitor_id == comp.id,
                            CompetitorPost.telegram_message_id.isnot(None),
                        )
                    )
                ).scalars().all()
            )
            new_posts = [p for p in posts if p.get("message_id") not in existing_ids]
            for p in new_posts:
                session.add(
                    CompetitorPost(
                        competitor_id=comp.id,
                        telegram_message_id=p.get("message_id"),
                        text_preview=p.get("text_preview") or (p.get("text") or "")[:500],
                        format=p.get("format") if p.get("format") in {"text", "photo", "video", "poll", "link"} else None,
                        views=p.get("views"),
                        forwards=p.get("forwards"),
                        reactions_count=p.get("reactions") or p.get("reactions_count"),
                        er=p.get("er"),
                        posted_at=p.get("posted_at"),
                    )
                )
            # Recompute avg ER from all stored posts
            all_posts = (
                await session.execute(
                    select(CompetitorPost).where(CompetitorPost.competitor_id == comp.id)
                )
            ).scalars().all()
            if all_posts:
                ers = [p.er for p in all_posts if p.er is not None]
                comp_row = (
                    await session.execute(select(Competitor).where(Competitor.id == comp.id))
                ).scalar_one_or_none()
                if comp_row and ers:
                    comp_row.avg_er = round(sum(ers) / len(ers), 3)
            await session.commit()
        updated += 1

    return {"competitors_refreshed": updated}


async def get_hot_competitor_topics(
    channel_id: str | uuid.UUID, days: int = 7, top_n: int = 10
) -> list[str]:
    """Keywords from high-ER competitor posts in the last `days` days.

    Used by strategy to identify what topics are resonating with competitor
    audiences RIGHT NOW — not just what themes competitors cover historically.
    """
    cid = uuid.UUID(str(channel_id))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        comp_ids = (
            await session.execute(
                select(Competitor.id).where(
                    Competitor.channel_id == cid,
                    Competitor.subscriber_count.isnot(None),
                )
            )
        ).scalars().all()
        if not comp_ids:
            return []
        posts = (
            await session.execute(
                select(CompetitorPost)
                .where(
                    CompetitorPost.competitor_id.in_(comp_ids),
                    CompetitorPost.er.isnot(None),
                    CompetitorPost.posted_at >= cutoff,
                )
                .order_by(CompetitorPost.er.desc())
                .limit(30)
            )
        ).scalars().all()

    _STOPWORDS = {
        "the", "and", "for", "are", "was", "has", "have", "get", "our", "your",
        "this", "that", "with", "from", "they", "will", "you", "can", "but",
        "not", "what", "all", "when", "how", "more", "also", "just", "been",
    }
    word_counts: dict[str, int] = defaultdict(int)
    for p in posts:
        text = (p.text_preview or "").lower()
        for word in re.findall(r"\b[a-z]{4,}\b", text):
            if word not in _STOPWORDS:
                word_counts[word] += 1
    return [w for w, _ in sorted(word_counts.items(), key=lambda kv: kv[1], reverse=True)][:top_n]
