from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    API_ID: int
    API_HASH: str
    PHONE_NUMBER: str

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/telegram_agent"

    SESSION_NAME: str = "telegram_growth_agent"
    POST_LIMIT: int = 500
    COLLECTION_INTERVAL_HOURS: int = 6

    # Metrics: rolling window of post history to analyse, and the minimum age a
    # post must reach before its view-dependent metrics are considered settled.
    LOOKBACK_DAYS: int = 90
    POST_MATURITY_HOURS: int = 24

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    SESSION_DIR: Path = BASE_DIR / "data" / "sessions"
    LOG_DIR: Path = BASE_DIR / "data" / "logs"


settings = Settings()
