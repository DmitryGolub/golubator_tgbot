from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    REDIS_PASSWORD: str | None = None
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

    # Notion internal API (for backfill script only)
    NOTION_TOKEN_V2: str | None = None
    NOTION_SPACE_ID: str | None = None

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "dev"  # "dev" | "json"

    GENERAL_CHAT_ID: int | None = None

    TEST_MODE: bool = False

    # CalDAV sync (one-way Meeting → personal calendar for mentors)
    CALDAV_ENABLED: bool = False
    CALDAV_ENCRYPTION_KEY: str | None = None
    # CSV of older Fernet keys (kept for read-only decryption during rotation)
    CALDAV_ENCRYPTION_KEYS_FALLBACK: str | None = None
    CALDAV_SYNC_INTERVAL_SECONDS: int = 60
    CALDAV_HOSTNAME: str = "golubator.pigeon.careers"
    CALDAV_HTTP_TIMEOUT_SECONDS: int = 15
    # Pull (CalDAV → PG): separate flag so it can be staged after push.
    CALDAV_PULL_ENABLED: bool = False
    CALDAV_PULL_INTERVAL_SECONDS: int = 60

    @model_validator(mode="after")
    def _validate_caldav(self) -> "Settings":
        if self.CALDAV_ENABLED and not self.CALDAV_ENCRYPTION_KEY:
            raise ValueError(
                "CALDAV_ENABLED=True requires CALDAV_ENCRYPTION_KEY "
                '(generate via `python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"`)'
            )
        return self

    @property
    def caldav_fallback_keys(self) -> list[str]:
        if not self.CALDAV_ENCRYPTION_KEYS_FALLBACK:
            return []
        return [
            k.strip()
            for k in self.CALDAV_ENCRYPTION_KEYS_FALLBACK.split(",")
            if k.strip()
        ]

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Синхронный URL для Alembic миграций"""
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def REDIS_URL(self) -> str:
        auth = f":{quote(self.REDIS_PASSWORD, safe='')}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/0"

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
