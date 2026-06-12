from telethon import TelegramClient
from telethon.tl.types import Channel

from app.telegram.fetcher import fetch_channel_metadata
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class MetadataService:
    def __init__(self, client: TelegramClient):
        self.client = client

    async def collect(self, entity: Channel, resolved: dict) -> dict:
        logger.info("Collecting channel metadata")
        metadata = await fetch_channel_metadata(self.client, entity, resolved)
        logger.info("Metadata collected for channel: %s", metadata.get("title", ""))
        return metadata



