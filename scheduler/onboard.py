"""Onboard a channel and run its tier-appropriate initial pipeline.

    python -m scheduler.onboard --channel @mychannel [--category deals] [--goal "reach 50k"]

Tier A (new, <5k):   competitor -> strategy
Tier B/C (5k+):      DNA -> competitor -> analytics -> strategy
"""
from __future__ import annotations

import argparse
import asyncio
import json

from scheduler.jobs import onboard_channel_pipeline
from tools.channels import get_or_create_channel


async def _main(username: str, category: str | None, goal: str | None) -> None:
    channel = await get_or_create_channel(username, category=category, growth_goal=goal)
    result = await onboard_channel_pipeline(channel["id"])
    print(json.dumps({"channel_id": channel["id"], **result}, indent=2, default=str))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Onboard a channel (tier-aware pipeline)")
    p.add_argument("--channel", required=True, help="Telegram @username")
    p.add_argument("--category", default=None)
    p.add_argument("--goal", default=None)
    args = p.parse_args()
    asyncio.run(_main(args.channel, args.category, args.goal))
