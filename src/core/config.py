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
    ADMIN_USERNAMES: str | None = None

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def admin_usernames(self) -> set[str]:
        if not self.ADMIN_USERNAMES:
            return set()
        return {name.strip().lower() for name in self.ADMIN_USERNAMES.split(",") if name.strip()}


settings = Settings()
