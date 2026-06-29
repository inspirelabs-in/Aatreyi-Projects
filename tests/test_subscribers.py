"""Near-real-time subscriber polling — record + realtime delta."""
import uuid

import pytest
from sqlalchemy import delete, select

from db.base import AsyncSessionLocal
from db.models import Channel, SubscriberReading
from tools.channels import get_or_create_channel
from tools.subscribers import get_subscriber_realtime, record_subscriber_reading


@pytest.mark.asyncio
async def test_record_and_realtime_delta():
    ch = await get_or_create_channel("subpoll_test")
    cid = ch["id"]
    try:
        await record_subscriber_reading(cid, 10000)
        await record_subscriber_reading(cid, 10120)  # +120 later
        rt = await get_subscriber_realtime(cid)
        assert rt["subscriber_count"] == 10120
        assert rt["delta"] == 120
        assert rt["delta_pct"] == 1.2
        assert rt["samples"] == 2
        assert rt["updated_at"] is not None
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(delete(SubscriberReading).where(SubscriberReading.channel_id == uuid.UUID(cid)))
            ch_row = (await s.execute(select(Channel).where(Channel.id == uuid.UUID(cid)))).scalar_one()
            await s.delete(ch_row)
            await s.commit()


@pytest.mark.asyncio
async def test_realtime_empty_is_safe():
    ch = await get_or_create_channel("subpoll_empty")
    cid = ch["id"]
    try:
        rt = await get_subscriber_realtime(cid)
        assert rt["subscriber_count"] is None and rt["samples"] == 0
    finally:
        async with AsyncSessionLocal() as s:
            ch_row = (await s.execute(select(Channel).where(Channel.id == uuid.UUID(cid)))).scalar_one()
            await s.delete(ch_row)
            await s.commit()
