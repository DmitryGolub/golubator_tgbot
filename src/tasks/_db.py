from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import settings


@asynccontextmanager
async def celery_db():
    """Isolated engine + session factory for Celery tasks.

    Sets database globals so that DAO classmethod calls work,
    then cleans up in finally.
    """
    from src.core import database

    engine = create_async_engine(settings.DATABASE_URL)
    database._engine = engine
    database._session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        await engine.dispose()
        database._engine = None
        database._session_factory = None
