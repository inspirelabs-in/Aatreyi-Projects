"""Shared Telethon (MTProto) client factory.

Telethon needs a one-time interactive login to create the session file
(``<TELETHON_SESSION>.session``). Run ``python -m tools.login`` once; afterwards
the session is reused non-interactively by every agent.

If your network blocks the Telegram protocol (ISP/DPI), set TELEGRAM_PROXY in
.env (SOCKS5/HTTP/MTProxy) or connect through a VPN before logging in.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from telethon import TelegramClient
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

from config import settings


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

    Applies TELEGRAM_PROXY if set. Extra kwargs (e.g. connection_retries,
    timeout) pass through and override the proxy-derived connection class.
    """
    client_kwargs = _parse_proxy(settings.TELEGRAM_PROXY)
    client_kwargs.update(kwargs)  # caller overrides win
    return TelegramClient(
        settings.TELETHON_SESSION,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
        **client_kwargs,
    )


@asynccontextmanager
async def telethon_session():
    """Yield a connected, authorized Telethon client; disconnect on exit.

    Raises RuntimeError if no authorized session exists yet (run tools.login).
    """
    client = build_client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telethon session is not authorized. "
                "Run `python -m tools.login` once to sign in."
            )
        yield client
    finally:
        await client.disconnect()
