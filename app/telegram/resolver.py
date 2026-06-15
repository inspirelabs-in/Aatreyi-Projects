from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, ChannelInvalidError, UsernameNotOccupiedError
from telethon.tl.types import Channel

from app.config.schemas import ChannelResolved
from app.utils.exceptions import ChannelNotFoundError, PermissionDeniedError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def resolve_channel(client: TelegramClient, username: str) -> ChannelResolved:
    logger.info("Resolving Channel: %s", username)

    try:
        entity = await client.get_entity(username)
    except UsernameNotOccupiedError:
        raise ChannelNotFoundError(f"Channel '{username}' does not exist")
    except ChannelInvalidError:
        raise ChannelNotFoundError(f"'{username}' is not a valid channel")
    except ValueError:
        raise ChannelNotFoundError(f"'{username}' could not be resolved")
    except Exception as e:
        raise ChannelNotFoundError(f"Failed to resolve '{username}': {e}")

    if not isinstance(entity, Channel):
        raise ChannelNotFoundError(f"'{username}' is not a channel")

    try:
        await client.get_permissions(entity, await client.get_me())
    except ChannelPrivateError:
        raise PermissionDeniedError(f"Channel '{username}' is private")
    except Exception:
        pass

    participants = await client.get_participants(entity, limit=0)
    subscriber_count = getattr(entity, "participants_count", None) or participants.total

    logger.info("Resolved: %s (ID: %d, Subs: %d)", entity.title, entity.id, subscriber_count)

    return ChannelResolved(
        channel_id=entity.id,
        title=entity.title,
        username=entity.username or username.lstrip("@"),
        description=getattr(entity, "about", "") if hasattr(entity, "about") else "",
        subscriber_count=subscriber_count or 0,
        verified=getattr(entity, "verified", False),
        public_channel=entity.username is not None,
    )
