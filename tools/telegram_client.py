"""Shared Telethon (MTProto) client factory.

Telethon needs a one-time interactive login to create the session file
(``<TELETHON_SESSION>.session``). Run ``python -m tools.login`` once; afterwards
the session is reused non-interactively by every agent.

If your network blocks the Telegram protocol (ISP/DPI), set TELEGRAM_PROXY in
.env (SOCKS5/HTTP/MTProxy) or connect through a VPN before logging in.
"""
from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from telethon import TelegramClient
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate
from telethon.sessions import SQLiteSession

from config import settings


class _RobustSQLiteSession(SQLiteSession):
    """SQLiteSession with WAL mode and a 30-second busy timeout.

    Both the API and scheduler containers mount the same session file. Telethon's
    default SQLiteSession opens sqlite3 with timeout=0, which fails immediately
    when the scheduler holds a write lock (e.g. during reconnect). This subclass:
      - uses timeout=30 so callers wait up to 30s for the lock instead of dying
      - enables WAL journal mode (persisted in the file header) so concurrent
        readers never block each other even while one writer is active
    """

    def _cursor(self):
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.filename,
                check_same_thread=False,
                timeout=30,
            )
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA busy_timeout=30000")
            except Exception:
                pass
        return self._conn.cursor()


def _parse_proxy(raw: str | None):
    """Parse TELEGRAM_PROXY into (connection_cls, proxy) kwargs for TelegramClient.

    Returns a dict suitable to splat into TelegramClient(...). Empty/None -> {}.

    - socks5://[user:pass@]host:port  /  socks4://...  /  http://host:port
        -> uses python-socks dict form
    - mtproxy://host:port:secret_hex
        -> uses Telethon's native MTProxy connection
    """
    if not raw:
        return {}

    if raw.startswith("mtproxy://"):
        rest = raw[len("mtproxy://"):]
        host, port, secret = rest.split(":", 2)
        return {
            "connection": ConnectionTcpMTProxyRandomizedIntermediate,
            "proxy": (host, int(port), secret),
        }

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in {"socks5", "socks4", "http"}:
        raise ValueError(f"Unsupported TELEGRAM_PROXY scheme: {scheme!r}")
    proxy: dict = {
        "proxy_type": scheme,
        "addr": parts.hostname,
        "port": parts.port,
        "rdns": True,
    }
    if parts.username:
        proxy["username"] = parts.username
    if parts.password:
        proxy["password"] = parts.password
    return {"proxy": proxy}


def build_client(**kwargs) -> TelegramClient:
    """Construct (but do not connect) a Telethon client from settings.

    Prefers TG_SESSION_STRING env var (cloud/Railway/Render deploy) over the
    local .session file. Falls back to _RobustSQLiteSession for local dev.
    """
    from telethon.sessions import StringSession
    session_str = getattr(settings, "TG_SESSION_STRING", None)
    if session_str:
        session = StringSession(session_str)
    else:
        session = _RobustSQLiteSession(settings.TELETHON_SESSION)
    client_kwargs = _parse_proxy(settings.TELEGRAM_PROXY)
    client_kwargs.update(kwargs)
    return TelegramClient(
        session,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
        **client_kwargs,
    )


@asynccontextmanager
async def telethon_session():
    """Yield a connected, authorized Telethon client; disconnect on exit.

    Raises RuntimeError if no authorized session exists yet (run tools.login).
    Retries on transient SQLite lock errors (scheduler + API running concurrently).
    """
    last_exc: Exception | None = None
    for attempt in range(4):
        client = build_client()
        try:
            await client.connect()
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            await client.disconnect()
            if "database is locked" in str(exc).lower() and attempt < 3:
                await asyncio.sleep(1.5 ** attempt)
            else:
                raise
    if last_exc:
        raise last_exc

    try:
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telethon session is not authorized. "
                "Run `python -m tools.login` once to sign in."
            )
        yield client
    finally:
        await client.disconnect()
