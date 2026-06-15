from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Channel, Post, SubscriberSnapshot, TrackedChannel, ContentMetrics, PerformanceMetrics, GrowthMetrics, ChannelFeatures
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

    async def get_by_username(self, username: str) -> Channel | None:
        result = await self.session.execute(
            select(Channel).where(Channel.username == username)
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
        result = await self.session.execute(
            select(func.count(Post.post_id)).where(Post.channel_id == channel_id)
        )
        return result.scalar() or 0

    async def delete_post(self, post: Post) -> None:
        await self.session.delete(post)
        await self.session.commit()

    async def update_post(self, post: Post, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(post, key, value)
        await self.session.commit()


class MetricRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _upsert_daily(self, model, data: dict[str, Any]):
        """Insert or update the row for (channel_id, today). One snapshot per
        channel per day: re-running collection on the same day refreshes that
        day's row instead of appending a duplicate, while previous days remain
        as historical time-series rows."""
        today = date.today()
        try:
            result = await self.session.execute(
                select(model).where(
                    model.channel_id == data["channel_id"],
                    model.snapshot_date == today,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                existing.snapshot_date = today
                existing.calculated_at = datetime.now()
            else:
                existing = model(**data, snapshot_date=today)
                self.session.add(existing)
            await self.session.commit()
            return existing
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save {model.__tablename__}: {e}")

    async def upsert_content_metrics(self, data: dict[str, Any]):
        return await self._upsert_daily(ContentMetrics, data)

    async def upsert_performance_metrics(self, data: dict[str, Any]):
        return await self._upsert_daily(PerformanceMetrics, data)

    async def upsert_growth_metrics(self, data: dict[str, Any]):
        return await self._upsert_daily(GrowthMetrics, data)

    async def upsert_channel_features(self, data: dict[str, Any]):
        return await self._upsert_daily(ChannelFeatures, data)

    async def get_history(self, model, channel_id: int, limit: int = 90) -> Sequence[Any]:
        """Return a channel's metric snapshots, newest first (time series)."""
        result = await self.session.execute(
            select(model)
            .where(model.channel_id == channel_id)
            .order_by(model.snapshot_date.desc())
            .limit(limit)
        )
        return result.scalars().all()


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
