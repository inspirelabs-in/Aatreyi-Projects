"""LLM access for the generation tools.

Provider-pluggable but defaults to Groq (OpenAI-compatible chat completions).
Includes exponential backoff for rate limits (roadmap Phase 10 edge case).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


async def chat_complete(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 700,
    max_retries: int = 3,
) -> str:
    """Return the assistant message text. Raises on hard failure after retries."""
    if settings.LLM_PROVIDER == "groq":
        return await _groq_chat(system, user, model, temperature, max_tokens, max_retries)
    raise NotImplementedError(f"LLM_PROVIDER {settings.LLM_PROVIDER!r} not wired yet")


async def _groq_chat(system, user, model, temperature, max_tokens, max_retries) -> str:
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")
    payload = {
        "model": model or settings.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    delay = 2.0
    last_err: str = "unknown error"
    # Generous retries: Groq free-tier rate limits (429) are per-minute, so a
    # batch of content generations can trip them — wait it out rather than fail.
    attempts = max(max_retries, 6)
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(attempts):
            try:
                resp = await client.post(GROQ_URL, json=payload, headers=headers)
                if resp.status_code == 429:  # rate limited
                    # Honor Groq's Retry-After (seconds) when present; else backoff.
                    retry_after = resp.headers.get("retry-after")
                    wait = float(retry_after) if retry_after else delay
                    last_err = f"429 rate limited (waited {wait:.0f}s)"
                    await asyncio.sleep(min(wait, 30.0))
                    delay = min(delay * 2, 30.0)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
    raise RuntimeError(f"LLM call failed after {attempts} retries: {last_err}")


def parse_post_json(raw: str) -> dict[str, Any]:
    """Best-effort parse of a model reply into {post_text, cta, hashtags}.

    Accepts a JSON object (possibly fenced) or falls back to raw text.
    """
    text = raw.strip()
    if "```" in text:
        # strip code fences
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("{"):
                text = p
                break
            if p.startswith("json"):
                text = p[4:].strip()
                break
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("post_text"):
            return {
                "post_text": str(data["post_text"]).strip(),
                "cta": (data.get("cta") or "").strip(),
                "hashtags": [f"#{s}" for h in (data.get("hashtags") or []) if (s := str(h).lstrip("#").strip())],
            }
    except Exception:
        pass
    return {"post_text": raw.strip(), "cta": "", "hashtags": []}


def _strip_fences(text: str) -> str:
    text = text.strip()
    if "```" in text:
        for p in text.split("```"):
            p = p.strip()
            if p.startswith("{"):
                return p
            if p.startswith("json"):
                return p[4:].strip()
    return text


def parse_poll_json(raw: str) -> dict[str, Any]:
    """Parse a poll reply into {question, options:[...], hashtags}.

    Falls back to first line = question, remaining non-empty lines = options.
    """
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
        opts = [str(o).strip() for o in (data.get("options") or []) if str(o).strip()]
        if data.get("question") and len(opts) >= 2:
            return {
                "question": str(data["question"]).strip(),
                "options": opts[:10],  # Telegram allows up to 10
                "hashtags": [f"#{str(h).lstrip('#')}" for h in (data.get("hashtags") or [])],
            }
    except Exception:
        pass
    lines = [ln.strip("-•* ").strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) >= 3:
        return {"question": lines[0], "options": lines[1:5], "hashtags": []}
    return {"question": raw.strip()[:300], "options": ["Yes", "No"], "hashtags": []}
