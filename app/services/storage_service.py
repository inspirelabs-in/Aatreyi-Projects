from typing import Any, Sequence


from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Channel, Post, SubscriberSnapshot
from app.database.repositories import ChannelRepository, PostRepository, SubscriberRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class StorageService:
    def __init__(self, session: AsyncSession):
        self.channel_repo = ChannelRepository(session)
        self.post_repo = PostRepository(session)
        self.subscriber_repo = SubscriberRepository(session)

    async def save_channel(self, channel_data: dict[str, Any]) -> Channel:
        logger.info("Saving channel data")
        return await self.channel_repo.save_channel(channel_data)

    async def save_posts(self, posts_data: list[dict[str, Any]]) -> list[Post]:
        logger.info("Saving %d posts", len(posts_data))
        return await self.post_repo.save_posts(posts_data)

    async def save_snapshot(self, channel_id: int, subscriber_count: int) -> SubscriberSnapshot:
        logger.info("Saving subscriber snapshot: %d", subscriber_count)
        return await self.subscriber_repo.save_snapshot(channel_id, subscriber_count)

    async def get_channel(self, channel_id: int) -> Channel | None:
        return await self.channel_repo.get_channel(channel_id)

    async def get_posts(self, channel_id: int) -> Sequence[Post]:
        return await self.post_repo.get_posts(channel_id)

    async def get_snapshots(self, channel_id: int) -> Sequence[SubscriberSnapshot]:
        return await self.subscriber_repo.get_snapshots(channel_id)
