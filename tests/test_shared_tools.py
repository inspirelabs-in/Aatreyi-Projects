"""Phase 1 shared-tool tests.

- log_agent_run: real insert + update against the tga DB.
- get_telegram_channel_info / get_channel_posts: real Telegram API call,
  auto-skipped until `python -m tools.login` has created an authorized session.
"""
import uuid

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import AgentRun
from tools.shared import (
    get_channel_posts,
    get_telegram_channel_info,
    log_agent_run,
)
from tools.telegram_client import build_client

TEST_CHANNEL = "@telegram"  # large public channel, always available


@pytest.mark.asyncio
async def test_log_agent_run_insert_then_update():
    run_id = uuid.uuid4()

    await log_agent_run(
        channel_id=None,
        agent="channel_dna",
        trigger="manual",
        status="running",
        run_id=run_id,
        input_snapshot={"test": True},
    )
    await log_agent_run(
        channel_id=None,
        agent="channel_dna",
        trigger="manual",
        status="completed",
        run_id=run_id,
        output_summary={"ok": 1},
        duration_ms=42,
    )

    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one()
        assert row.status.value == "completed"
        assert row.duration_ms == 42
        assert row.finished_at is not None
        # cleanup
        await session.delete(row)
        await session.commit()


@pytest.mark.asyncio
async def test_get_channel_info_and_posts_real():
    # Low retry count so an unreachable network skips fast instead of hanging.
    client = build_client(connection_retries=1, retry_delay=0, timeout=10)
    try:
        await client.connect()
    except (ConnectionError, OSError) as exc:
        pytest.skip(f"Telegram unreachable from this environment: {exc}")
    try:
        if not await client.is_user_authorized():
            pytest.skip("No Telethon session — run `python -m tools.login` first.")

        info = await get_telegram_channel_info(client, TEST_CHANNEL)
        assert info["channel_id"]
        assert info["title"]

        result = await get_channel_posts(client, TEST_CHANNEL, days=365, limit=20)
        assert result["total_fetched"] > 0
        first = result["posts"][0]
        assert first["format"] in {
            "text", "photo", "video", "poll", "link", "document"
        }
        assert "posted_at" in first
    finally:
        await client.disconnect()
