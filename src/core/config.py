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
    ADMIN_IDS: str | None = None
    NOTION_TOKEN: str | None = None
    NOTION_DATABASE_ID: str | None = None

    YANDEX_SHEETS_TOKEN: str | None = None
    YANDEX_SHEETS_FILE_PATH: str | None = None
    YANDEX_SHEETS_SHEET_NAME: str = "feedback_export"
    YANDEX_SHEETS_BASE_URL: str = "https://cloud-api.yandex.net/v1/disk"
    YANDEX_SHEETS_TIMEOUT_SECONDS: float = 30.0

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
