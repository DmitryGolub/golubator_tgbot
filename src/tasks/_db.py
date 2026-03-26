import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import settings


def run_async(coro):
    """Run async coroutine in a fresh event loop (for Celery tasks).

    Preferred over asyncio.run() because it explicitly cleans up the
    current-thread event loop reference, avoiding stale loop issues
    when Celery reuses the same thread for subsequent tasks.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass


@asynccontextmanager
async def celery_db():
    """Isolated engine + session factory for Celery tasks.

    Sets database globals so that DAO classmethod calls work,
    then cleans up in finally.

    WARNING: This overwrites global database._engine and database._session_factory.
    Safe ONLY with -P solo worker pool (single-threaded). Using prefork or
    gevent pool will cause race conditions on these globals.
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
