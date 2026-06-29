"""Find a working MTProxy and (optionally) write it into .env.

Free public MTProxies rotate and die often. Run this when Telegram stops
connecting to grab a fresh working one:

    python -m tools.find_proxy            # print a working mtproxy:// URL
    python -m tools.find_proxy --write    # also update TELEGRAM_PROXY in .env

NOTE: public proxies are third-party infrastructure. MTProto traffic stays
end-to-end encrypted through them, but for production prefer a reputable VPN
or a self-hosted MTProxy.
"""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from telethon import TelegramClient
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate as MTProxy
from telethon.sessions import StringSession

from config import settings

SOURCES = [
    "https://raw.githubusercontent.com/SoliSpirit/mtproto/master/all_proxies.txt",
    "https://raw.githubusercontent.com/shablin/mtproto-proxy/master/data/valid_proxy.json",
]
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch_candidates() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    seen: set = set()
    for url in SOURCES:
        try:
            text = httpx.get(url, headers=HEADERS, timeout=25).text
        except Exception:
            continue
        for line in text.splitlines():
            q = parse_qs(urlparse(line.strip()).query)
            srv, port, sec = q.get("server"), q.get("port"), q.get("secret")
            if not (srv and port and sec):
                continue
            host, p, secret = srv[0], port[0], sec[0]
            if not re.fullmatch(r"[0-9a-fA-F]+", secret):
                continue  # hex secrets only (Telethon-compatible)
            key = (host, int(p), secret)
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


async def _handshake_ok(host: str, port: int, secret: str) -> bool:
    c = TelegramClient(
        StringSession(), settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH,
        connection=MTProxy, proxy=(host, port, secret),
        connection_retries=1, retry_delay=0, timeout=8,
    )
    try:
        await asyncio.wait_for(c.connect(), timeout=12)
        return c.is_connected()
    except Exception:
        return False
    finally:
        try:
            await c.disconnect()
        except Exception:
            pass


def _write_env(proxy_url: str) -> None:
    env = Path(".env")
    lines = env.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("TELEGRAM_PROXY="):
            lines[i] = f"TELEGRAM_PROXY={proxy_url}"
            break
    else:
        lines.append(f"TELEGRAM_PROXY={proxy_url}")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main(write: bool, limit: int) -> None:
    cands = _fetch_candidates()
    print(f"Testing up to {limit} of {len(cands)} candidates...")
    for i, (host, port, secret) in enumerate(cands[:limit], 1):
        ok = await _handshake_ok(host, port, secret)
        print(f"[{i}/{min(limit, len(cands))}] {host}:{port} -> {'WORKS' if ok else 'fail'}")
        if ok:
            url = f"mtproxy://{host}:{port}:{secret}"
            print(f"\nWORKING: {url}")
            if write:
                _write_env(url)
                print("Wrote TELEGRAM_PROXY to .env")
            return
    print("No working proxy found — try increasing --limit or use a VPN.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Find a working MTProxy")
    ap.add_argument("--write", action="store_true", help="update TELEGRAM_PROXY in .env")
    ap.add_argument("--limit", type=int, default=40, help="max candidates to test")
    args = ap.parse_args()
    asyncio.run(main(args.write, args.limit))
