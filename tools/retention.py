"""Retention engine (Phase 2 — habit loops, fatigue control, recycling).

Turns the Phase-1 signals into ACTIONS the strategy schedules:
  - habit-loop retention triggers (series, cliffhanger, weekly format, challenge)
  - content-fatigue scoring (too much repetition hurts retention)
  - recycle candidates (reuse break-out posts in a new format)

Pure functions — the strategy rule engine calls these to inject slots.
"""
from __future__ import annotations

from typing import Any

from tools.intelligence import post_er

# Habit-loop trigger catalogue. `kind` flows to the content generator, which
# produces the format-specific copy (Day-N series, open-loop teaser, etc.).
_TRIGGER_CATALOG = {
    "series":      {"format": "text", "topic": "Series · Day {day} — {topic}",
                    "why": "Multi-day storytelling creates a return habit (come back for the next day)."},
    "cliffhanger": {"format": "text", "topic": "Teaser — tomorrow: {topic}",
                    "why": "An open loop ('tomorrow I'll show…') pulls users back the next day."},
    "weekly":      {"format": "text", "topic": "Weekly roundup — {topic}",
                    "why": "A recurring appointment format trains habitual, scheduled returns."},
    "challenge":   {"format": "poll", "topic": "7-day challenge — {topic}",
                    "why": "Task-based commitment + daily check-ins build a strong retention loop."},
    "reengage":    {"format": "poll", "topic": "Re-engagement — which topics do you want more of?",
                    "why": "Direct win-back ask re-activates lapsing members and lifts ER."},
}


def build_retention_triggers(churn_risk: str | None, community_state: str | None,
                             primary_topic: str | None, series_day: int = 1) -> list[dict[str, Any]]:
    """Pick habit-loop triggers by severity (most urgent first). Higher risk =>
    more aggressive loops. The first trigger becomes the plan's first slot.
    `series_day` advances the series across runs (Day 1 -> Day 2 -> ...)."""
    topic = primary_topic or "your niche"
    picked: list[str] = []
    if churn_risk == "high" or community_state == "silent":
        picked += ["reengage", "challenge"]      # urgent win-back first
    if churn_risk in ("medium", "high") or community_state == "silent":
        picked += ["series", "cliffhanger"]
    picked += ["weekly"]                          # a recurring format always helps habit formation

    seen, triggers = set(), []
    for kind in picked:
        if kind in seen:
            continue
        seen.add(kind)
        spec = _TRIGGER_CATALOG[kind]
        triggers.append({
            "kind": kind,
            "format": spec["format"],
            "topic": spec["topic"].format(topic=topic, day=series_day),
            "why": spec["why"],
        })
    return triggers


def fatigue_score(tasks: list[dict]) -> dict[str, Any]:
    """Content-fatigue score in [0,1]: how often adjacent slots repeat the same
    format or topic. High repetition reduces retention."""
    if len(tasks) < 2:
        return {"score": 0.0, "format_adjacent_repeats": 0, "topic_adjacent_repeats": 0, "flags": []}
    pairs = list(zip(tasks, tasks[1:]))
    fmt_rep = sum(1 for a, b in pairs if a.get("format") == b.get("format"))
    topic_rep = sum(1 for a, b in pairs if a.get("topic") == b.get("topic"))
    score = round((fmt_rep + topic_rep) / (2 * len(pairs)), 3)
    flags = []
    if fmt_rep / len(pairs) > 0.6:
        flags.append("same format repeated back-to-back")
    if topic_rep / len(pairs) > 0.4:
        flags.append("same topic repeated back-to-back")
    return {"score": score, "format_adjacent_repeats": fmt_rep,
            "topic_adjacent_repeats": topic_rep, "flags": flags}


def recycle_candidates(posts: list[dict], top_n: int = 3) -> list[dict[str, Any]]:
    """Break-out past posts worth recycling (repost in a fresh format/time)."""
    ranked = sorted(posts, key=post_er, reverse=True)
    out = []
    for p in ranked[:top_n]:
        er = round(post_er(p), 2)
        if er <= 0:
            continue
        text = (p.get("text") or "").strip()
        out.append({
            "text_preview": text[:90],
            "text": text[:500],
            "er": er,
            "suggestion": "Recycle: repost in a new format (text→image/poll) at a fresh slot.",
        })
    return out
