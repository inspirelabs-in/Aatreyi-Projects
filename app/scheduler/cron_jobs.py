from telethon import TelegramClient

from app.config.settings import settings
from app.database.session import async_session_factory
from app.services.channel_service import ChannelService
from app.services.storage_service import StorageService
from app.telegram.auth import authenticate
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def collect_all_channels() -> None:
    logger.info("Scheduled collection started")

    client = TelegramClient(
        str(settings.SESSION_DIR / settings.SESSION_NAME),
        settings.API_ID,
        settings.API_HASH,
    )

    try:
        client = await authenticate(client)

        async with async_session_factory() as session:
            storage = StorageService(session)
            channels = await storage.get_active_channels()

        if not channels:
            logger.warning("No active tracked channels found")
            return

        logger.info("Found %d active channels to collect", len(channels))

        service = ChannelService(client)
        for tc in channels:
            try:
                await service.collect(tc.username)
            except Exception as e:
                logger.error("Failed to collect %s: %s", tc.username, e)

        logger.info("Scheduled collection completed for %d channels", len(channels))

    except Exception as e:
        logger.error("Scheduled collection failed: %s", e)
    finally:
        await client.disconnect()
