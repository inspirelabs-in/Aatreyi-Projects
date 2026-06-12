"""
Run: python debug_channel.py @channelname
Prints the raw Telegram response so you can see exactly what is happening.
"""
import asyncio
import sys
from telethon import TelegramClient
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.functions.channels import GetFullChannelRequest

# ── paste your credentials here ──────────────────────────────────────────────
API_ID   = 39466369
API_HASH = "dc0906edcdc9d6a84d6600f53bb52de6"
PHONE    = "+919726174705"
SESSION  = "data/sessions/telegram_growth_agent"
# ─────────────────────────────────────────────────────────────────────────────

async def debug(username: str):
    clean = username.lstrip("@").strip()
    print(f"\n{'='*55}")
    print(f"  Debugging: @{clean}")
    print(f"{'='*55}\n")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("Session not authorised — run the main pipeline once to log in first.")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Logged in as: +{me.phone}\n")

    # ── Test 1: ResolveUsernameRequest ────────────────────────────────────────
    print(f"[TEST 1] ResolveUsernameRequest('{clean}') ...")
    try:
        result = await client(ResolveUsernameRequest(clean))
        print(f"  SUCCESS")
        print(f"  result.chats  : {result.chats}")
        print(f"  result.users  : {result.users}")
        if result.chats:
            ch = result.chats[0]
            print(f"\n  Channel found:")
            print(f"    type         : {type(ch).__name__}")
            print(f"    id           : {ch.id}")
            print(f"    title        : {ch.title}")
            print(f"    username     : {ch.username}")
            print(f"    access_hash  : {ch.access_hash}")
            print(f"    broadcast    : {getattr(ch, 'broadcast', 'n/a')}")
            print(f"    megagroup    : {getattr(ch, 'megagroup', 'n/a')}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")

    print()

    # ── Test 2: get_entity fallback ───────────────────────────────────────────
    print(f"[TEST 2] client.get_entity('@{clean}') ...")
    try:
        entity = await client.get_entity(f"@{clean}")
        print(f"  SUCCESS")
        print(f"    type     : {type(entity).__name__}")
        print(f"    id       : {entity.id}")
        print(f"    title    : {getattr(entity, 'title', 'n/a')}")
        print(f"    username : {getattr(entity, 'username', 'n/a')}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")

    print()

    # ── Test 3: direct URL search ─────────────────────────────────────────────
    print(f"[TEST 3] Searching Telegram for '{clean}' ...")
    try:
        from telethon.tl.functions.contacts import SearchRequest
        results = await client(SearchRequest(q=clean, limit=5))
        print(f"  Found {len(results.chats)} chats, {len(results.users)} users")
        for c in results.chats[:3]:
            print(f"    chat: {getattr(c, 'username', '?')} — {getattr(c, 'title', '?')}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")

    print()
    await client.disconnect()
    print("Done.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_channel.py @channelname")
        sys.exit(1)
    asyncio.run(debug(sys.argv[1]))