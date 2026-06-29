"""Central configuration. All env vars are read here and nowhere else.

Usage:
    from config import settings
    print(settings.DATABASE_URL_SYNC)   # alembic / scripts
    print(settings.DATABASE_URL_ASYNC)  # app runtime
"""
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _swap_scheme(url: str, driver: str) -> str:
    """Force a postgres DSN onto a specific driver scheme.

    Accepts any of postgres://, postgresql://, postgresql+asyncpg://,
    postgresql+psycopg:// and rewrites to `postgresql+<driver>://`.
    """
    parts = urlsplit(url)
    return urlunsplit(parts._replace(scheme=f"postgresql+{driver}"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Telegram (Telethon / MTProto user login) ─────────────────────────────
    TELEGRAM_API_ID: int = Field(..., description="my.telegram.org api_id")
    TELEGRAM_API_HASH: str = Field(..., description="my.telegram.org api_hash")
    PHONE_NUMBER: str | None = Field(
        default=None, description="Phone for first-time Telethon login (+CC...)"
    )
    TELETHON_SESSION: str = Field(
        default="tga_user", description="Telethon session file name (no extension)"
    )
    # Route MTProto around ISP/DPI blocking. Formats:
    #   socks5://[user:pass@]host:port   socks4://host:port   http://host:port
    #   mtproxy://host:port:secret_hex
    # Leave empty to connect directly (or use a VPN, which needs no value here).
    TELEGRAM_PROXY: str | None = None
    # Proxy for WEB SCRAPING (Amazon/Flipkart Playwright + httpx article fetches).
    # Datacenter IPs (Railway/Render) get blocked by Amazon/Flipkart, so set a
    # residential/scraping proxy here in production. Format:
    #   http://user:pass@host:port  |  socks5://user:pass@host:port
    # Leave empty for direct (works fine locally / on residential IPs).
    SCRAPER_PROXY: str | None = None
    # Bot API token — only needed for publishing/review bot (Phase 6/7).
    BOT_TOKEN: str | None = None
    ADMIN_TELEGRAM_ID: int | None = None

    # ── LLM (Phase 6) ────────────────────────────────────────────────────────
    # Plan specifies Anthropic Claude; a Groq key is also supported as an
    # alternate provider. Either may be set — neither is needed before Phase 6.
    ANTHROPIC_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    LLM_MODEL: str = Field(default="claude-sonnet-4-6")
    # Active generation provider for generate_post / generate_original_post.
    LLM_PROVIDER: str = Field(default="groq", description="groq | anthropic")
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")

    # ── Datastores ─────────────────────────────────────────────────────────────
    # Provide one DSN in any postgres scheme; sync/async forms are derived below.
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/tga"
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # ── Supplementary analytics APIs (optional) ──────────────────────────────
    TGSTAT_API_KEY: str | None = None
    TELEMETR_API_KEY: str | None = None
    # Pexels image API for photo post thumbnails (free at pexels.com/api).
    PEXELS_API_KEY: str | None = None

    # ── Live deal scraping (deals-aggregator channels, e.g. GrabOn) ──────────
    # Affiliate tags appended to scraped product links. Amazon default is the
    # team tag; Flipkart left blank until the tech team provides one.
    AMAZON_AFFILIATE_TAG: str = Field(default="tlg022-21")
    FLIPKART_AFFILIATE_TAG: str | None = None
    # Full Flipkart affiliate query string appended after the product path
    # (replaces the product's own ?pid=...&lid=... query). affid + tracking params.
    FLIPKART_AFFILIATE_PARAMS: str = Field(default="affid=bh7162&affExtParam1=1005&affExtParam2=gb")
    # Discount policy: prefer >= PREFERRED%, fall back no lower than MIN%.
    DEAL_PREFERRED_DISCOUNT: int = Field(default=80)
    DEAL_MIN_DISCOUNT: int = Field(default=65)
    # Platforms to scrape and how many deals per category to keep.
    DEAL_PLATFORMS: str = Field(default="Amazon,Flipkart")
    DEAL_MAX_PER_CATEGORY: int = Field(default=3)
    # Hour (local/IST, 0-23) for the dedicated daily deals refresh job.
    DEAL_REFRESH_HOUR: int = Field(default=8)

    # ── Content scoring defaults ─────────────────────────────────────────────
    SCORE_THRESHOLD: int = Field(default=4)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    # Cron jobs (daily insights+strategy, weekly/monthly refresh) fire in this
    # timezone. Defaults to IST; override with any IANA name (UTC, America/New_York…).
    SCHEDULER_TIMEZONE: str = Field(default="Asia/Kolkata")
    # Hour (local, 0-23) for the daily Analytics->Strategy cycle. 7 = 7 AM.
    DAILY_CYCLE_HOUR: int = Field(default=7)
    # How often the content dispatcher checks for due post slots (minutes).
    CONTENT_DISPATCH_INTERVAL_MIN: int = Field(default=5)
    # How often to sample subscriber counts (minutes) — near-real-time growth.
    SUBSCRIBER_POLL_INTERVAL_MIN: int = Field(default=10)

    # ── Deployment ────────────────────────────────────────────────────────────
    # Comma-separated CORS origins. Set to "*" in production behind nginx.
    ALLOWED_ORIGINS: str | None = None
    # Telethon string session (alternative to the .session file for cloud deploy).
    # Generate with: python -m tools.export_session
    TG_SESSION_STRING: str | None = None

    # ── Monitoring (optional) ─────────────────────────────────────────────────
    SENTRY_DSN: str | None = None

    @field_validator(
        "PHONE_NUMBER",
        "TELEGRAM_PROXY",
        "SCRAPER_PROXY",
        "BOT_TOKEN",
        "ADMIN_TELEGRAM_ID",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "TGSTAT_API_KEY",
        "TELEMETR_API_KEY",
        "PEXELS_API_KEY",
        "FLIPKART_AFFILIATE_TAG",
        "SENTRY_DSN",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v):
        """Treat empty env strings (e.g. ``BOT_TOKEN=``) as unset."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """psycopg (v3) DSN — used by Alembic and sync scripts."""
        return _swap_scheme(self.DATABASE_URL, "psycopg")

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        """asyncpg DSN — used by FastAPI handlers and async agents."""
        return _swap_scheme(self.DATABASE_URL, "asyncpg")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
