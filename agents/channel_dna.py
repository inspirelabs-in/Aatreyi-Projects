"""Channel DNA Agent (Phase 2).

Profiles a channel: ER, posting times, format mix, tone, category — and persists
to channel_dna. Tier B/C channels run this; Tier A skips straight to competitors.

    python -m agents.channel_dna --channel @techdigest_in
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from agents.base import BaseAgent
from tools.channel_dna import (
    MIN_POSTS_AGENT_GATE,
    compute_channel_dna,
    detect_tier,
    get_disappearing_message_flag,
    get_tgstat_channel_stats,
    llm_classify_category,
    llm_extract_topics,
    save_channel_dna,
)
from tools.channels import get_or_create_channel, update_channel_meta
from tools.shared import get_channel_posts, get_telegram_channel_info
from tools.telegram_client import telethon_session


class ChannelDNAAgent(BaseAgent):
    name = "channel_dna"

    async def _execute(
        self, channel_id: str, *, username: str, client=None, **_: Any
    ) -> dict[str, Any]:
        # 1. resolve channel metadata (always step 1 — need channel_id + members)
        if client is not None:
            result = await self._run_with_client(channel_id, username, client)
        else:
            async with telethon_session() as c:
                result = await self._run_with_client(channel_id, username, c)
        return result

    async def _run_with_client(self, channel_id, username, client) -> dict[str, Any]:
        info = await get_telegram_channel_info(client, username)
        posts = (await get_channel_posts(client, username, days=90))["posts"]
        tgstat = await get_tgstat_channel_stats(username)  # supplementary, may be {}

        tier = detect_tier(info.get("member_count"))
        await update_channel_meta(
            channel_id,
            telegram_id=info.get("channel_id"),
            display_name=info.get("title"),
            tier=tier,
        )

        # agent gate: too few posts to compute full metrics -> save a partial
        # record. Still try to classify a category (keywords, then LLM) so even
        # a low-volume channel gets a useful label instead of a blank one.
        if len(posts) < MIN_POSTS_AGENT_GATE:
            from tools.channel_dna import get_channel_category
            cat, sub = get_channel_category(posts, username)
            if not cat:
                cat, sub = await llm_classify_category(posts, username)
            partial = {
                "subscriber_count": info.get("member_count"),
                "insufficient_data": True,
                "category": cat,
                "sub_category": sub,
            }
            saved = await save_channel_dna(channel_id, partial)
            if cat:
                await update_channel_meta(channel_id, category=cat, sub_category=sub)
            return {
                "insufficient_data": True,
                "posts_found": len(posts),
                "category": cat,
                "record_id": saved["record_id"],
                "tier": tier,
            }

        dna = compute_channel_dna(
            posts=posts,
            member_count=info.get("member_count"),
            tgstat_data=tgstat,
            username=username,
        )
        dna["has_disappearing_messages"] = get_disappearing_message_flag(info)
        # keyword rules are narrow — if they were inconclusive, ask the LLM to
        # classify into one of the known categories (handles e.g. an
        # "entertainment" channel whose posts lack the literal keyword list).
        if not dna.get("category"):
            cat, sub = await llm_classify_category(posts, username)
            if cat:
                dna["category"] = cat
                dna["sub_category"] = dna.get("sub_category") or sub
        # prefer accurate LLM-extracted topics; fall back to rule-based mining
        llm_topics = await llm_extract_topics(posts, dna.get("category"))
        if llm_topics:
            dna["top_topics"] = llm_topics
        saved = await save_channel_dna(channel_id, dna)
        # propagate detected category to the channel row (dashboard reads it)
        await update_channel_meta(
            channel_id, category=dna.get("category"), sub_category=dna.get("sub_category")
        )

        return {
            "insufficient_data": False,
            "tier": tier,
            "subscriber_count": dna["subscriber_count"],
            "avg_er": dna["avg_er"],
            "best_post_hour": dna["best_post_hour"],
            "category": dna["category"],
            "record_id": saved["record_id"],
            "dna": dna,
        }

    def _summarize(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            k: result.get(k)
            for k in ("tier", "subscriber_count", "avg_er", "category", "insufficient_data")
        }


async def _main(username: str) -> None:
    channel = await get_or_create_channel(username)
    agent = ChannelDNAAgent(trigger="manual")
    result = await agent.run(channel["id"], username=username)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Channel DNA Agent")
    parser.add_argument("--channel", required=True, help="Telegram @username")
    args = parser.parse_args()
    asyncio.run(_main(args.channel))
