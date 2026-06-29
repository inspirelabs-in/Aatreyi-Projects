"""One-time interactive Telethon login.

    python -m tools.login

Sends a login code to your Telegram app, then writes the session file so all
agents can use the Telegram API non-interactively afterward.
"""
import asyncio

from config import settings
from tools.telegram_client import build_client


async def main() -> None:
    client = build_client()
    # start() handles the interactive code / 2FA password prompts.
    await client.start(phone=settings.PHONE_NUMBER)
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username}) id={me.id}")
    print(f"Session saved to: {settings.TELETHON_SESSION}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
