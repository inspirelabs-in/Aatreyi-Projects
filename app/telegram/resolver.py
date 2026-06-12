from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.types import Channel

from app.utils.exceptions import ChannelNotFoundError, PermissionDeniedError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def resolve_channel(client: TelegramClient, channel_username: str) -> dict:
    logger.info("Resolving Channel: %s", channel_username)

    # Strip @ so we pass a clean username to Telegram
    clean_username = channel_username.lstrip("@").strip()

    try:
        # ResolveUsernameRequest does a direct network lookup — it never
        # relies on local cache, so it works even for channels the session
        # has never interacted with before.
        result = await client(ResolveUsernameRequest(clean_username))

    except UsernameNotOccupiedError:
        raise ChannelNotFoundError(
            f"'{channel_username}' does not exist on Telegram. "
            "Check the username spelling — it is case-insensitive but must be exact."
        )
    except UsernameInvalidError:
        raise ChannelNotFoundError(
            f"'{channel_username}' is not a valid Telegram username. "
            "Usernames can only contain letters, numbers, and underscores."
        )
    except FloodWaitError as e:
        raise ChannelNotFoundError(
            f"Telegram rate limit hit during resolution. "
            f"Wait {e.seconds} seconds and try again."
        )
    except Exception as e:
        raise ChannelNotFoundError(
            f"Failed to resolve '{channel_username}': {type(e).__name__}: {e}"
        )

    # result.chats contains the channel object when the username is a channel
    if not result.chats:
        raise ChannelNotFoundError(
            f"'{channel_username}' exists on Telegram but is not a channel. "
            "It may be a bot or a user account."
        )

    entity = result.chats[0]

    if not isinstance(entity, Channel):
        raise ChannelNotFoundError(
            f"'{channel_username}' is not a broadcast channel "
            f"(found type: {type(entity).__name__}). "
            "This tool only supports channels, not groups."
        )

    # Check accessibility — private channels will raise ChannelPrivateError
    try:
        await client.get_permissions(entity, await client.get_me())
    except ChannelPrivateError:
        raise PermissionDeniedError(
            f"'{channel_username}' is a private channel. "
            "You must be a member or admin to analyse it."
        )
    except Exception:
        # Non-fatal — proceed even if permission check fails
        pass

    logger.info(
        "Channel Resolved: %s (ID: %s, Verified: %s)",
        entity.title,
        entity.id,
        getattr(entity, "verified", False),
    )

    return {
        "channel_id": entity.id,
        "access_hash": entity.access_hash,
        "title": entity.title,
        "username": entity.username or clean_username,
        "verified": getattr(entity, "verified", False),
    }
