from telethon import TelegramClient

from app.config.settings import settings


async def get_telegram_client() -> TelegramClient:
    session_path = settings.SESSION_DIR / settings.SESSION_NAME
    settings.SESSION_DIR.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(
        str(session_path),
        settings.API_ID,
        settings.API_HASH,
    )
    return client
