import logging

from src.core.redis import get_redis
from src.dao.ui_text import UiTextDAO

logger = logging.getLogger(__name__)

_PREFIX = "ui_text:"
_TTL = 300  # 5 minutes


class UiTextService:
    @staticmethod
    async def get(key: str, **kwargs: str) -> str:
        r = get_redis()
        cached = await r.get(f"{_PREFIX}{key}")
        if cached is not None:
            value = cached
        else:
            row = await UiTextDAO.get_by_key(key)
            if row is None:
                logger.warning("UiText key not found: %s", key)
                return key
            value = row.value
            await r.set(f"{_PREFIX}{key}", value, ex=_TTL)

        if kwargs:
            try:
                return value.format(**kwargs)
            except KeyError:
                logger.warning("UiText format error for key=%s kwargs=%s", key, kwargs)
                return value
        return value

    @staticmethod
    async def get_many(keys: list[str]) -> dict[str, str]:
        r = get_redis()
        cache_keys = [f"{_PREFIX}{k}" for k in keys]
        cached_values = await r.mget(cache_keys)

        result: dict[str, str] = {}
        missing: list[str] = []

        for key, cached in zip(keys, cached_values):
            if cached is not None:
                result[key] = cached
            else:
                missing.append(key)

        if missing:
            from_db = await UiTextDAO.get_many(missing)
            pipe = r.pipeline()
            for key in missing:
                value = from_db.get(key, key)
                result[key] = value
                pipe.set(f"{_PREFIX}{key}", value, ex=_TTL)
            await pipe.execute()

        return result

    @staticmethod
    async def invalidate(key: str) -> None:
        r = get_redis()
        await r.delete(f"{_PREFIX}{key}")

    @staticmethod
    async def update(key: str, value: str) -> None:
        await UiTextDAO.update_value(key, value)
        await UiTextService.invalidate(key)
