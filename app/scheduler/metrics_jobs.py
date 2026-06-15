from app.database.repositories import ChannelRepository
from app.database.session import async_session_factory
from app.services.metrics_service import MetricsService
from app.services.storage_service import StorageService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def recalculate_metrics_for_channel(channel_id: int, subscribers: int) -> None:
    async with async_session_factory() as session:
        metrics_service = MetricsService(session)
        await metrics_service.process_channel(channel_id=channel_id, subscribers=subscribers)


async def recalculate_all_metrics() -> None:
    async with async_session_factory() as session:
        storage = StorageService(session)
        channel_repo = ChannelRepository(session)
        channels = await storage.get_active_channels()
        logger.info("Recalculating metrics for %d channels", len(channels))
        for tc in channels:
            channel = await channel_repo.get_by_username(tc.username)
            if not channel:
                logger.warning("No channel record for tracked username %s", tc.username)
                continue
            snapshots = await storage.subscriber_repo.get_by_channel(channel.channel_id)
            subscribers = snapshots[0].subscriber_count if snapshots else 0
            await recalculate_metrics_for_channel(channel.channel_id, subscribers)
        logger.info("Recalculation complete")
