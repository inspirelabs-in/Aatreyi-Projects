from datetime import date
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Channel,
    Post,
    SubscriberSnapshot,
    ContentMetrics,
    PerformanceMetrics,
    RegisteredChannel,
    AnalysisResult,
)
from app.utils.exceptions import DatabaseError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_channel(self, channel_data: dict[str, Any]) -> Channel:
        try:
            existing = await self.get_channel(channel_data["channel_id"])
            if existing:
                for key, value in channel_data.items():
                    setattr(existing, key, value)
                await self.session.commit()
                logger.info("Channel updated: %s (%s)", existing.title, existing.channel_id)
                return existing

            channel = Channel(**channel_data)
            self.session.add(channel)
            await self.session.commit()
            logger.info("Channel saved: %s (%s)", channel.title, channel.channel_id)
            return channel
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save channel: {e}")

    async def get_channel(self, channel_id: int) -> Channel | None:
        result = await self.session.execute(
            select(Channel).where(Channel.channel_id == channel_id)
        )
        return result.scalar_one_or_none()


class RegisteredChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_channel(self, channel_username: str, alias: str | None = None) -> RegisteredChannel:
        normalized_username = self._normalize_username(channel_username)
        existing = await self.get_channel(normalized_username)
        if existing:
            existing.alias = alias or existing.alias
            existing.active = True
            await self.session.commit()
            return existing

        channel = RegisteredChannel(
            channel_username=normalized_username,
            alias=alias,
            active=True,
        )
        self.session.add(channel)
        await self.session.commit()
        return channel

    async def get_channel(self, channel_username: str) -> RegisteredChannel | None:
        result = await self.session.execute(
            select(RegisteredChannel).where(
                RegisteredChannel.channel_username == self._normalize_username(channel_username)
            )
        )
        return result.scalar_one_or_none()

    async def get_active_channels(self) -> Sequence[RegisteredChannel]:
        result = await self.session.execute(
            select(RegisteredChannel)
            .where(RegisteredChannel.active.is_(True))
            .order_by(RegisteredChannel.id.asc())
        )
        return result.scalars().all()

    async def list_channels(self) -> Sequence[RegisteredChannel]:
        result = await self.session.execute(
            select(RegisteredChannel).order_by(RegisteredChannel.id.asc())
        )
        return result.scalars().all()

    async def deactivate_channel(self, channel_username: str) -> bool:
        existing = await self.get_channel(channel_username)
        if not existing:
            return False
        existing.active = False
        await self.session.commit()
        return True

    async def update_last_run_at(self, channel_username: str, timestamp) -> RegisteredChannel | None:
        existing = await self.get_channel(channel_username)
        if existing:
            existing.last_run_at = timestamp
            await self.session.commit()
        return existing

    @staticmethod
    def _normalize_username(channel_username: str) -> str:
        if not channel_username:
            return ""
        normalized = channel_username.strip()
        if not normalized.startswith("@"):
            normalized = "@" + normalized
        return normalized


class PostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_posts(self, posts_data: list[dict[str, Any]]) -> list[Post]:
        saved: list[Post] = []
        try:
            for post_data in posts_data:
                existing = await self.get_post(post_data["message_id"])
                if existing:
                    continue

                post = Post(**post_data)
                self.session.add(post)
                saved.append(post)

            await self.session.commit()
            logger.info("Saved %d new posts", len(saved))
            return saved
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save posts: {e}")

    async def get_post(self, message_id: int) -> Post | None:
        result = await self.session.execute(
            select(Post).where(Post.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def get_posts(self, channel_id: int) -> Sequence[Post]:
        result = await self.session.execute(
            select(Post).where(Post.channel_id == channel_id).order_by(Post.timestamp.desc())
        )
        return result.scalars().all()


class SubscriberRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_snapshot(self, channel_id: int, subscriber_count: int) -> SubscriberSnapshot:
        try:
            today = date.today()
            existing = await self.get_snapshot(channel_id, today)
            if existing:
                existing.subscriber_count = subscriber_count
                await self.session.commit()
                logger.info("Snapshot updated for channel %s: %d subscribers", channel_id, subscriber_count)
                return existing

            snapshot = SubscriberSnapshot(
                channel_id=channel_id,
                subscriber_count=subscriber_count,
                snapshot_date=today,
            )
            self.session.add(snapshot)
            await self.session.commit()
            logger.info("Snapshot saved for channel %s: %d subscribers", channel_id, subscriber_count)
            return snapshot
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save subscriber snapshot: {e}")

    async def get_snapshot(self, channel_id: int, snapshot_date: date | None = None) -> SubscriberSnapshot | None:
        if snapshot_date is None:
            snapshot_date = date.today()
        result = await self.session.execute(
            select(SubscriberSnapshot).where(
                SubscriberSnapshot.channel_id == channel_id,
                SubscriberSnapshot.snapshot_date == snapshot_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_snapshots(self, channel_id: int) -> Sequence[SubscriberSnapshot]:
        result = await self.session.execute(
            select(SubscriberSnapshot)
            .where(SubscriberSnapshot.channel_id == channel_id)
            .order_by(SubscriberSnapshot.snapshot_date.desc())
        )
        return result.scalars().all()


class ContentMetricsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_metrics(self, metrics_data: dict[str, Any]) -> ContentMetrics:
        try:
            metrics = ContentMetrics(**metrics_data)
            self.session.add(metrics)
            await self.session.commit()
            logger.info("Content metrics saved for channel %s", metrics_data["channel_id"])
            return metrics
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save content metrics: {e}")

    async def get_latest_metrics(self, channel_id: int) -> ContentMetrics | None:
        result = await self.session.execute(
            select(ContentMetrics)
            .where(ContentMetrics.channel_id == channel_id)
            .order_by(ContentMetrics.calculated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_metrics_history(self, channel_id: int, limit: int = 30) -> Sequence[ContentMetrics]:
        result = await self.session.execute(
            select(ContentMetrics)
            .where(ContentMetrics.channel_id == channel_id)
            .order_by(ContentMetrics.calculated_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


class PerformanceMetricsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_metrics(self, metrics_data: dict[str, Any]) -> PerformanceMetrics:
        try:
            metrics = PerformanceMetrics(**metrics_data)
            self.session.add(metrics)
            await self.session.commit()
            logger.info("Performance metrics saved for channel %s", metrics_data["channel_id"])
            return metrics
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save performance metrics: {e}")

    async def get_latest_metrics(self, channel_id: int) -> PerformanceMetrics | None:
        result = await self.session.execute(
            select(PerformanceMetrics)
            .where(PerformanceMetrics.channel_id == channel_id)
            .order_by(PerformanceMetrics.calculated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_metrics_history(self, channel_id: int, limit: int = 30) -> Sequence[PerformanceMetrics]:
        result = await self.session.execute(
            select(PerformanceMetrics)
            .where(PerformanceMetrics.channel_id == channel_id)
            .order_by(PerformanceMetrics.calculated_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


class AnalysisResultRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_result(
        self,
        channel_username: str,
        stage: str,
        payload: dict[str, Any],
        channel_id: int | None = None,
    ) -> AnalysisResult:
        try:
            result = AnalysisResult(
                channel_id=channel_id,
                channel_username=channel_username,
                stage=stage,
                payload=payload,
            )
            self.session.add(result)
            await self.session.commit()
            logger.info("Saved analysis result for %s stage %s", channel_username, stage)
            return result
        except Exception as e:
            await self.session.rollback()
            raise DatabaseError(f"Failed to save analysis result: {e}")

    async def get_latest_result(self, channel_username: str, stage: str) -> AnalysisResult | None:
        result = await self.session.execute(
            select(AnalysisResult)
            .where(
                AnalysisResult.channel_username == channel_username,
                AnalysisResult.stage == stage,
            )
            .order_by(AnalysisResult.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

