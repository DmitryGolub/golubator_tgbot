import re

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_URL_SAFE_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    BOT_TOKEN: str

    DB_NAME: str
    DB_USER: str
    DB_PASS: str
    DB_HOST: str
    DB_PORT: str

    REDIS_HOST: str
    REDIS_PORT: int
    ADMIN_IDS: str | None = None
    NOTION_TOKEN: str | None = None
    NOTION_DATABASE_ID: str | None = None

    # Notion multi-database sync
    NOTION_MENTOR_DB_ID: str | None = None
    NOTION_MENTEE_DB_ID: str | None = None
    NOTION_EVENT_DB_ID: str | None = None
    NOTION_MENTEE_TEMPLATE_PAGE_ID: str | None = None
    # Push interval: PostgreSQL → Notion (seconds)
    NOTION_PUSH_INTERVAL: int = 30
    # Backup polling intervals: Notion → PostgreSQL (seconds)
    NOTION_BACKUP_POLL_USERS_INTERVAL: int = 1800
    NOTION_BACKUP_POLL_EVENTS_INTERVAL: int = 600
    NOTION_WEBHOOK_SECRET: str | None = None

    @model_validator(mode="after")
    def _validate_webhook_secret(self) -> "Settings":
        secret = self.NOTION_WEBHOOK_SECRET
        if secret and not _URL_SAFE_RE.match(secret):
            raise ValueError(
                "NOTION_WEBHOOK_SECRET must contain only URL-safe characters: "
                "A-Z, a-z, 0-9, hyphen, underscore"
            )
        return self

    # Notion internal API (for backfill script only)
    NOTION_TOKEN_V2: str | None = None
    NOTION_SPACE_ID: str | None = None

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "dev"  # "dev" | "json"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Синхронный URL для Alembic миграций"""
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def admin_ids(self) -> set[int]:
        if not self.ADMIN_IDS:
            return set()
        return {
            int(id_.strip())
            for id_ in self.ADMIN_IDS.split(",")
            if id_.strip().isdigit()
        }


settings = Settings()
