from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Channel, Post, SubscriberSnapshot, TrackedChannel
from app.utils.exceptions import DatabaseError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TrackedChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active(self) -> Sequence[TrackedChannel]:
        result = await self.session.execute(
            select(TrackedChannel).where(TrackedChannel.active == True)
        )
        return result.scalars().all()

    async def add(self, username: str) -> TrackedChannel:
        existing = await self.session.execute(
            select(TrackedChannel).where(TrackedChannel.username == username)
        )
        if existing.scalar_one_or_none():
            raise DatabaseError(f"Channel {username} is already tracked")
        tc = TrackedChannel(username=username, active=True)
        self.session.add(tc)
        await self.session.commit()
        logger.info("Tracked channel added: %s", username)
        return tc

    async def deactivate(self, username: str) -> None:
        result = await self.session.execute(
            select(TrackedChannel).where(TrackedChannel.username == username)
        )
        tc = result.scalar_one_or_none()
        if tc:
            tc.active = False
            await self.session.commit()
            logger.info("Tracked channel deactivated: %s", username)


class ChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, data: dict[str, Any]) -> Channel:
        try:
            existing = await self.get(data["channel_id"])
            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                await self.session.commit()
                return existing
            channel = Channel(**data)
            self.session.add(channel)
            await self.session.commit()
            return channel
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save channel: {e}")

    async def get(self, channel_id: int) -> Channel | None:
        result = await self.session.execute(
            select(Channel).where(Channel.channel_id == channel_id)
        )
        return result.scalar_one_or_none()


class PostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_many(self, posts_data: list[dict[str, Any]]) -> int:
        inserted = 0
        try:
            for data in posts_data:
                existing = await self.session.execute(
                    select(Post).where(
                        Post.post_id == data["post_id"],
                        Post.channel_id == data["channel_id"],
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                self.session.add(Post(**data))
                inserted += 1
            await self.session.commit()
            logger.info("Inserted %d new posts", inserted)
            return inserted
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save posts: {e}")

    async def get_by_channel(self, channel_id: int) -> Sequence[Post]:
        result = await self.session.execute(
            select(Post).where(Post.channel_id == channel_id).order_by(Post.timestamp.desc())
        )
        return result.scalars().all()

    async def count_by_channel(self, channel_id: int) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count(Post.post_id)).where(Post.channel_id == channel_id)
        )
        return result.scalar() or 0


class SubscriberRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_snapshot(self, channel_id: int, count: int) -> SubscriberSnapshot:
        try:
            today = date.today()
            existing = await self.session.execute(
                select(SubscriberSnapshot).where(
                    SubscriberSnapshot.channel_id == channel_id,
                    SubscriberSnapshot.snapshot_date == today,
                )
            )
            snap = existing.scalar_one_or_none()
            if snap:
                snap.subscriber_count = count
            else:
                snap = SubscriberSnapshot(channel_id=channel_id, subscriber_count=count)
                self.session.add(snap)
            await self.session.commit()
            return snap
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save snapshot: {e}")

    async def get_by_channel(self, channel_id: int) -> Sequence[SubscriberSnapshot]:
        result = await self.session.execute(
            select(SubscriberSnapshot)
            .where(SubscriberSnapshot.channel_id == channel_id)
            .order_by(SubscriberSnapshot.snapshot_date.desc())
        )
        return result.scalars().all()
