from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker as sa_async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings


_engine: AsyncEngine | None = None
_session_factory: sa_async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.DATABASE_URL)
    return _engine


def async_session_maker() -> AsyncSession:
    global _session_factory
    if _session_factory is None:
        _session_factory = sa_async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory()


class Base(DeclarativeBase):
    pass
