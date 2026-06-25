"""Analytics Agent (Phase 4).

Daily/weekly performance snapshots: growth, ER, reach, churn signal, insights.
Flags an out-of-cycle Strategy run on churn or ER-drop.

    python -m agents.analytics --channel @techdigest_in --type daily
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta
from typing import Any

from agents.base import BaseAgent
from tools.analytics import (
    compute_analytics_snapshot,
    flag_strategy_review,
    generate_analytics_digest,
    get_analytics_history,
    get_previous_snapshot,
    get_target_post_frequency,
    save_analytics_snapshot,
)
from tools.channels import get_or_create_channel
from tools.intelligence import compute_post_intelligence
from tools.retention import recycle_candidates
from tools.shared import get_channel_posts, get_telegram_channel_info
from tools.telegram_client import telethon_session

_TRIGGER_BY_TYPE = {"daily": "cron_daily", "weekly": "cron_weekly", "monthly": "cron_monthly"}


class AnalyticsAgent(BaseAgent):
    name = "analytics"

    def __init__(self, snapshot_type: str = "daily", trigger: str | None = None):
        super().__init__(trigger=trigger or _TRIGGER_BY_TYPE.get(snapshot_type, "manual"))
        self.snapshot_type = snapshot_type

    async def _execute(self, channel_id: str, *, username: str, client=None, **_: Any) -> dict[str, Any]:
        if client is not None:
            return await self._run(channel_id, username, client)
        async with telethon_session() as c:
            return await self._run(channel_id, username, c)

    async def _run(self, channel_id, username, client) -> dict[str, Any]:
        days = {"daily": 1, "weekly": 7, "monthly": 30}.get(self.snapshot_type, 1)
        info = await get_telegram_channel_info(client, username)
        posts = (await get_channel_posts(client, username, days=days))["posts"]

        previous = await get_previous_snapshot(channel_id, self.snapshot_type)
        history = await get_analytics_history(channel_id, self.snapshot_type, n=30)
        target_freq = await get_target_post_frequency(channel_id)

        period_end = date.today()
        period_start = period_end - timedelta(days=days - 1)
        snapshot = compute_analytics_snapshot(
            channel_id=channel_id,
            current_member_count=info.get("member_count") or 0,
            posts=posts,
            previous_snapshot=previous,
            snapshot_type=self.snapshot_type,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            history=history,
            target_post_frequency=target_freq,
        )
        # Phase 1: post & audience intelligence (virality, purpose mix, community
        # signal) + recycle candidates — persisted alongside the snapshot.
        intel = compute_post_intelligence(posts, info.get("member_count") or 0)
        intel["recycle_candidates"] = recycle_candidates(posts)
        snapshot["intelligence"] = intel

        # Patch subscriber_delta from high-frequency readings when snapshot comparison
        # yields None (e.g. previous snapshot was backfilled history with no subscriber_count).
        if snapshot.get("subscriber_delta") is None:
            from tools.subscribers import get_subscriber_realtime
            rt = await get_subscriber_realtime(channel_id)
            if rt.get("delta") is not None:
                snapshot["subscriber_delta"] = rt["delta"]
                if snapshot.get("subscriber_delta_pct") is None:
                    snapshot["subscriber_delta_pct"] = rt.get("delta_pct")

        saved = await save_analytics_snapshot(channel_id, snapshot)

        # trigger early strategy review on churn or ER drop
        insight_types = {i["type"] for i in snapshot["insights"]}
        review_reason = None
        if snapshot["churn_signal"]:
            review_reason = "churn_signal"
        elif "er_drop" in insight_types:
            review_reason = "er_drop_30pct"
        if review_reason:
            await flag_strategy_review(channel_id, review_reason)

        return {
            "record_id": saved["record_id"],
            "snapshot_type": self.snapshot_type,
            "subscriber_count": snapshot["subscriber_count"],
            "subscriber_delta": snapshot["subscriber_delta"],
            "avg_er": snapshot["avg_er"],
            "churn_signal": snapshot["churn_signal"],
            "insights": snapshot["insights"],
            "intelligence": intel,
            "flagged_strategy_review": review_reason,
            "digest": generate_analytics_digest(snapshot),
        }

    def _summarize(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            k: result.get(k)
            for k in ("snapshot_type", "subscriber_delta", "avg_er", "churn_signal", "flagged_strategy_review")
        }


async def _main(username: str, snapshot_type: str) -> None:
    channel = await get_or_create_channel(username)
    agent = AnalyticsAgent(snapshot_type=snapshot_type)
    result = await agent.run(channel["id"], username=username)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Analytics Agent")
    parser.add_argument("--channel", required=True, help="Telegram @username")
    parser.add_argument("--type", default="daily", choices=["daily", "weekly", "monthly"])
    args = parser.parse_args()
    asyncio.run(_main(args.channel, args.type))
