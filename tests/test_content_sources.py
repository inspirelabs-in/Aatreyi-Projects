"""Content source seeding + CRUD tests."""
import uuid

import pytest
from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, ContentSource
from tools.channels import get_or_create_channel
from tools.content_sources import add_source, list_sources, seed_default_sources


@pytest.mark.asyncio
async def test_seed_default_sources_by_category():
    channel = await get_or_create_channel("src_seed_deals", category="deals")
    cid = channel["id"]
    try:
        res = await seed_default_sources(cid, "deals")
        assert res["seeded"] >= 1
        rows = await list_sources(cid)
        assert rows and rows[0]["type"] == "rss"
        again = await seed_default_sources(cid, "deals")
        assert again["seeded"] == 0
    finally:
        await _cleanup(cid)


@pytest.mark.asyncio
async def test_add_and_list_source():
    channel = await get_or_create_channel("src_add_channel", category="tech")
    cid = channel["id"]
    try:
        created = await add_source(cid, type="rss", url="https://example.com/feed.xml", name="Example")
        assert created["id"]
        rows = await list_sources(cid)
        assert len(rows) == 1 and rows[0]["name"] == "Example"
    finally:
        await _cleanup(cid)


async def _cleanup(cid):
    async with AsyncSessionLocal() as s:
        ch = (await s.execute(select(Channel).where(Channel.id == uuid.UUID(cid)))).scalar_one()
        await s.delete(ch)
        await s.commit()
