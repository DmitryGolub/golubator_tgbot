from redis.asyncio import ConnectionPool, Redis

from src.core.config import settings

_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool


def get_redis() -> Redis:
    return Redis(connection_pool=get_redis_pool())
