from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories import ChannelRepository, PostRepository, SubscriberRepository, TrackedChannelRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class StorageService:
    def __init__(self, session: AsyncSession):
        self.tracked_repo = TrackedChannelRepository(session)
        self.channel_repo = ChannelRepository(session)
        self.post_repo = PostRepository(session)
        self.subscriber_repo = SubscriberRepository(session)

    async def save_channel(self, data: dict[str, Any]) -> None:
        await self.channel_repo.upsert(data)
        logger.info("Channel saved: %s", data.get("title", ""))

    async def save_posts(self, posts: list[dict[str, Any]]) -> int:
        return await self.post_repo.upsert_many(posts)

    async def save_snapshot(self, channel_id: int, count: int) -> None:
        await self.subscriber_repo.upsert_snapshot(channel_id, count)
        logger.info("Snapshot saved: channel=%d count=%d", channel_id, count)

    async def get_active_channels(self) -> list[Any]:
        return await self.tracked_repo.get_active()
