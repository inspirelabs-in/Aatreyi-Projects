from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    PhoneNumberBannedError,
)

from app.config.settings import settings
from app.utils.exceptions import AuthenticationError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def authenticate(client: TelegramClient) -> TelegramClient:
    logger.info("Authentication Started")

    if not client.is_connected():
        await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        logger.info("Authentication Success (session reused) - User: %s", me.phone)
        return client

    try:
        await client.send_code_request(settings.PHONE_NUMBER)
        logger.info("OTP sent to %s", settings.PHONE_NUMBER)

        code = input("Enter the OTP code sent to your Telegram: ").strip()

        try:
            await client.sign_in(settings.PHONE_NUMBER, code)
        except SessionPasswordNeededError:
            password = input("Two-factor authentication enabled. Enter your password: ").strip()
            await client.sign_in(password=password)

        me = await client.get_me()
        logger.info("Authentication Success - User: %s", me.phone)
        return client

    except PhoneNumberInvalidError:
        raise AuthenticationError("Invalid phone number. Check PHONE_NUMBER in .env")
    except PhoneNumberBannedError:
        raise AuthenticationError("Phone number is banned from Telegram")
    except PhoneCodeInvalidError:
        raise AuthenticationError("Invalid OTP code entered")
    except Exception as e:
        raise AuthenticationError(f"Authentication failed: {e}")
