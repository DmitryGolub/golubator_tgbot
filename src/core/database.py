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


def init_engine() -> None:
    """Eagerly initialize the global engine + session factory.

    Idempotent. Called once at Celery worker bootstrap inside the worker
    event loop so the asyncpg pool binds to that loop, and reused by all
    subsequent DAO calls. In the bot process the engine is created lazily
    via get_engine() instead.
    """
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    if _session_factory is None:
        _session_factory = sa_async_sessionmaker(
            _engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )


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
