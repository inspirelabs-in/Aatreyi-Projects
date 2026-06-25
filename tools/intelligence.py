"""Post & audience intelligence (Phase 1 — aggregate, channel-level).

Pure functions over the metrics Telethon exposes for a broadcast channel
(views, forwards, reactions) — there is no per-user data, so this works at the
post/aggregate level: virality scoring, post-purpose classification, topic &
format retention proxies, and community-signal / silent-channel detection.

All functions are side-effect free and unit-testable without network/DB.
"""
from __future__ import annotations

import re
from statistics import median
from typing import Any

_LINK_RE = re.compile(r"https?://|t\.me/", re.I)
_CTA_RE = re.compile(
    r"\b(join|subscribe|register|sign ?up|buy|grab|claim|download|enroll|apply|book|"
    r"comment|share|forward|vote|click|link in)\b", re.I
)
_HASHTAG_RE = re.compile(r"#(\w{2,30})")

# thresholds (engagement % of views)
SPIKE_MULTIPLIER = 2.0          # ER >= 2x median => break-out post
GROWTH_FORWARD_RATE = 3.0       # forwards >= 3% of views => growth/viral
RETENTION_REACTION_RATE = 5.0   # reactions >= 5% of views => sticky/retention
SILENT_REACTION_FLOOR = 0.5     # avg reaction density below this => "silent channel"


def _views(p: dict) -> int:
    return p.get("views") or 0


def _reactions(p: dict) -> int:
    return p.get("reactions") or p.get("reactions_count") or 0


def _forwards(p: dict) -> int:
    return p.get("forwards") or 0


def post_er(post: dict) -> float:
    """(reactions + forwards) / views * 100 — matches the competitor ER formula."""
    return (_reactions(post) + _forwards(post)) / max(_views(post), 1) * 100.0


def forward_rate(post: dict) -> float:
    return round(_forwards(post) / max(_views(post), 1) * 100.0, 3)


def reaction_density(post: dict) -> float:
    return round(_reactions(post) / max(_views(post), 1) * 100.0, 3)


def classify_post_purpose(post: dict) -> str:
    """Classify a post by its dominant signal:
    growth (gets forwarded), retention (sticky reactions/poll), conversion
    (drives action via CTA/link), or standard.
    """
    fmt = (post.get("format") or "").lower()
    text = post.get("text") or ""
    if fmt == "poll" or reaction_density(post) >= RETENTION_REACTION_RATE:
        return "retention"
    if forward_rate(post) >= GROWTH_FORWARD_RATE:
        return "growth"
    if fmt == "link" or _LINK_RE.search(text) or _CTA_RE.search(text):
        return "conversion"
    return "standard"


def detect_spikes(posts: list[dict]) -> list[int]:
    """Indices of break-out posts whose ER >= SPIKE_MULTIPLIER x the median ER."""
    ers = [post_er(p) for p in posts]
    if len(ers) < 3:
        return []
    med = median(ers)
    if med <= 0:
        return []
    return [i for i, e in enumerate(ers) if e >= SPIKE_MULTIPLIER * med]


def _avg_er_by(posts: list[dict], key) -> list[dict]:
    buckets: dict[str, list[float]] = {}
    for p in posts:
        for k in key(p):
            buckets.setdefault(k, []).append(post_er(p))
    out = [
        {"label": k, "avg_er": round(sum(v) / len(v), 3), "posts": len(v)}
        for k, v in buckets.items()
    ]
    return sorted(out, key=lambda d: d["avg_er"], reverse=True)


def score_formats_by_engagement(posts: list[dict]) -> list[dict]:
    """Which content FORMAT engages best (proxy for retention) — feeds the mix."""
    return _avg_er_by(posts, lambda p: [(p.get("format") or "text").lower()])


def score_topics_by_engagement(posts: list[dict]) -> list[dict]:
    """Which topics (hashtags) engage best — proxy for topic→retention dependency."""
    return _avg_er_by(posts, lambda p: [h.lower() for h in _HASHTAG_RE.findall(p.get("text") or "")])


def community_signal(posts: list[dict], member_count: int | None = None) -> dict[str, Any]:
    """Social-proof / silent-channel detection from reaction & forward density."""
    if not posts:
        return {"reaction_density": 0.0, "forward_rate": 0.0, "poll_participation": None,
                "silent": True, "state": "no_data"}
    rd = round(sum(reaction_density(p) for p in posts) / len(posts), 3)
    fr = round(sum(forward_rate(p) for p in posts) / len(posts), 3)
    polls = [p for p in posts if (p.get("format") or "").lower() == "poll"]
    poll_part = None
    if polls and member_count:
        voters = [(p.get("total_voters") or 0) for p in polls]
        poll_part = round(sum(voters) / len(voters) / max(member_count, 1) * 100.0, 3) if any(voters) else None
    silent = rd < SILENT_REACTION_FLOOR and fr < SILENT_REACTION_FLOOR
    state = "silent" if silent else ("active" if rd >= 2.0 else "quiet")
    return {"reaction_density": rd, "forward_rate": fr, "poll_participation": poll_part,
            "silent": silent, "state": state}


def compute_post_intelligence(posts: list[dict], member_count: int | None = None) -> dict[str, Any]:
    """Aggregate post-intelligence blob for one analytics period."""
    if not posts:
        return {"posts_analyzed": 0, "purpose_mix": {}, "spikes": 0,
                "format_engagement": [], "topic_engagement": [],
                "community_signal": community_signal([], member_count)}
    purposes = [classify_post_purpose(p) for p in posts]
    mix: dict[str, int] = {}
    for p in purposes:
        mix[p] = mix.get(p, 0) + 1
    spikes = detect_spikes(posts)
    return {
        "posts_analyzed": len(posts),
        "purpose_mix": mix,                                   # growth/retention/conversion/standard counts
        "spikes": len(spikes),
        "format_engagement": score_formats_by_engagement(posts)[:6],
        "topic_engagement": score_topics_by_engagement(posts)[:8],
        "community_signal": community_signal(posts, member_count),
    }
