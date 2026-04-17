from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from src.core.redis import get_redis


@asynccontextmanager
async def try_page_lock(key: str, ttl: int = 30) -> AsyncIterator[bool]:
    """Try to acquire a non-blocking Redis lock.

    Yields True if the lock was acquired (and will be released on exit),
    False if another worker already holds it.
    """
    redis = get_redis()
    acquired = await redis.set(key, "1", nx=True, ex=ttl)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            await redis.delete(key)
