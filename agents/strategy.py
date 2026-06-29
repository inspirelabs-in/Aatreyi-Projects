"""Strategy Agent (Phase 5).

Builds a slot-level action plan from DNA + analytics + competitors, persists the
strategy and its tasks, and registers content-agent post-slot crons.

    python -m agents.strategy --channel @techdigest_in --type weekly

No live Telegram needed — it reads everything from the DB.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta
from typing import Any

from agents.base import BaseAgent
from tools.channels import get_or_create_channel
from tools.strategy import (
    archive_old_strategy,
    compute_strategy,
    load_strategy_inputs,
    save_strategy,
    update_cron_for_content_agent,
)
from tools.strategy_llm import llm_enrich_strategy

_TRIGGER_BY_TYPE = {"daily": "cron_daily", "weekly": "cron_weekly", "monthly": "cron_monthly"}


class StrategyAgent(BaseAgent):
    name = "strategy"

    def __init__(self, strategy_type: str = "weekly", trigger: str | None = None):
        super().__init__(trigger=trigger or _TRIGGER_BY_TYPE.get(strategy_type, "manual"))
        self.strategy_type = strategy_type

    async def _execute(self, channel_id: str, **_: Any) -> dict[str, Any]:
        inputs = await load_strategy_inputs(channel_id)
        if not inputs.get("channel"):
            raise ValueError(f"Channel {channel_id} not found")

        # period STARTS TODAY so today's slots exist and can be generated right
        # away. daily -> just today; weekly -> today + next 6; monthly -> today + 29.
        days = {"daily": 1, "weekly": 7, "monthly": 30}.get(self.strategy_type, 7)
        ps = date.today()
        pe = ps + timedelta(days=days - 1)

        # archive any overlapping active strategy first (preserves approved/published)
        await archive_old_strategy(channel_id, strategy_type=self.strategy_type)

        payload = compute_strategy(
            inputs, strategy_type=self.strategy_type,
            period_start=ps.isoformat(), period_end=pe.isoformat(),
        )
        # Strategist pass: an LLM reads the channel's own posts + competitors' best
        # posts and rewrites the soft parts of the plan (goal, tactics, per-slot
        # topic/format/angle). No-ops back to the rule-based plan on any failure.
        payload = await llm_enrich_strategy(channel_id, payload, inputs)
        payload["strategy_type"] = self.strategy_type
        saved = await save_strategy(channel_id, payload)
        cron = await update_cron_for_content_agent(channel_id, payload["tasks"])

        return {
            "strategy_id": saved["strategy_id"],
            "total_slots": saved["tasks_created"],
            "slots_per_day": round(payload["post_frequency_per_day"]),
            "content_mix": payload["content_mix"],
            "primary_topics": payload["primary_topics"],
            "growth_tactics": payload["growth_tactics"],
            "growth_recommendations": payload.get("growth_recommendations"),
            "retention_recommendations": payload.get("retention_recommendations"),
            "cron_jobs_created": cron["cron_jobs_created"],
            "period_start": payload["period_start"],
            "period_end": payload["period_end"],
        }

    def _summarize(self, result: dict[str, Any]) -> dict[str, Any]:
        return {k: result.get(k) for k in ("strategy_id", "total_slots", "slots_per_day")}


async def _main(username: str, strategy_type: str) -> None:
    channel = await get_or_create_channel(username)
    agent = StrategyAgent(strategy_type=strategy_type)
    result = await agent.run(channel["id"])
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Strategy Agent")
    parser.add_argument("--channel", required=True, help="Telegram @username")
    parser.add_argument("--type", default="weekly", choices=["daily", "weekly", "monthly"])
    args = parser.parse_args()
    asyncio.run(_main(args.channel, args.type))
