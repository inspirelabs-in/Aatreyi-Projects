import asyncio
from typing import Any

from app.database.db import AsyncSessionLocal, init_db
from app.database.repositories import RegisteredChannelRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def register_channel(channel_username: str, alias: str | None = None) -> dict[str, Any]:
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = RegisteredChannelRepository(session)
        channel = await repo.add_channel(channel_username, alias)
        logger.info("Registered channel: %s", channel.channel_username)
        return {
            "id": channel.id,
            "channel_username": channel.channel_username,
            "alias": channel.alias,
            "active": channel.active,
            "created_at": channel.created_at,
        }


async def unregister_channel(channel_username: str) -> bool:
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = RegisteredChannelRepository(session)
        result = await repo.deactivate_channel(channel_username)
        if result:
            logger.info("Unregistered channel: %s", channel_username)
        else:
            logger.warning("Channel not found for unregister: %s", channel_username)
        return result


async def list_registered_channels() -> list[dict[str, Any]]:
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = RegisteredChannelRepository(session)
        channels = await repo.list_channels()
        return [
            {
                "id": channel.id,
                "channel_username": channel.channel_username,
                "alias": channel.alias,
                "active": channel.active,
                "created_at": channel.created_at,
                "last_run_at": channel.last_run_at,
            }
            for channel in channels
        ]
