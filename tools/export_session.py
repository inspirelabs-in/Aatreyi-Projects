"""Convert the local tga_user.session file to a string for cloud deployment.

Run once on your local machine:
    python -m tools.export_session

Copy the printed string into your Railway / Render / cloud env var:
    TG_SESSION_STRING=<the printed string>
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import settings


async def main() -> None:
    client = TelegramClient(
        settings.TELETHON_SESSION,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: Session not authorized. Run `python -m tools.login` first.")
        await client.disconnect()
        return
    session_string = StringSession.save(client.session)
    await client.disconnect()
    print("\n" + "=" * 60)
    print("TG_SESSION_STRING (add this as an env var in Railway/Render):")
    print("=" * 60)
    print(session_string)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
