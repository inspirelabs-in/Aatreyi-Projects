from telethon import TelegramClient
from telethon.tl.types import Channel


from app.telegram.fetcher import fetch_subscriber_count
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class SubscriberService:
    def __init__(self, client: TelegramClient):
        self.client = client

    async def collect(self, entity: Channel) -> int:
        logger.info("Collecting subscriber count")
        count = await fetch_subscriber_count(self.client, entity)
        logger.info("Subscriber count collected: %d", count)
        return count
