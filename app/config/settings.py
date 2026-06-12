from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    API_ID: int
    API_HASH: str
    PHONE_NUMBER: str

    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/telegram"

    SESSION_NAME: str = "telegram_growth_agent"
    POST_FETCH_LIMIT: int = 500
    POST_FETCH_BATCH_SIZE: int = 100
    COLLECTION_INTERVAL_HOURS: int = 6
    ALERT_INTERVAL_MINUTES: int = 30
    SCHEDULER_CRON: str = "0 */6 * * *"
    SCHEDULER_TIMEZONE: str = "UTC"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TEMPERATURE: float = 0.2
    OPENAI_MAX_TOKENS: int = 1800

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    SESSION_DIR: Path = Path("data/sessions")
    LOG_DIR: Path = Path("data/logs")
    DATA_DIR: Path = Path("data/database")

    @property
    def sync_database_url(self) -> str:
        return self.DATABASE_URL.replace("+aiosqlite", "").replace("+asyncpg", "")


settings = Settings()
