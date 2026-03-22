import json

from src.core.redis import get_redis

_PERMS_PREFIX = "perms:"
_ROLE_PREFIX = "role:"
_TTL = 300  # 5 minutes


async def get_cached_permissions(user_id: int) -> set[str] | None:
    r = get_redis()
    raw = await r.get(f"{_PERMS_PREFIX}{user_id}")
    if raw is None:
        return None
    return set(json.loads(raw))


async def set_cached_permissions(user_id: int, perms: set[str]) -> None:
    r = get_redis()
    await r.set(
        f"{_PERMS_PREFIX}{user_id}", json.dumps(sorted(perms)), ex=_TTL
    )


async def get_cached_role(user_id: int) -> dict | None:
    r = get_redis()
    raw = await r.get(f"{_ROLE_PREFIX}{user_id}")
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached_role(user_id: int, role_data: dict) -> None:
    r = get_redis()
    await r.set(f"{_ROLE_PREFIX}{user_id}", json.dumps(role_data), ex=_TTL)


async def invalidate_user_cache(user_id: int) -> None:
    r = get_redis()
    await r.delete(f"{_PERMS_PREFIX}{user_id}", f"{_ROLE_PREFIX}{user_id}")


async def invalidate_role_cache(role_id: int) -> None:
    """Invalidate cache for all users with given role_id."""
    from src.models.user import User

    from sqlalchemy import select
    from src.core.database import async_session_maker

    async with async_session_maker() as session:
        result = await session.execute(
            select(User.telegram_id).where(User.role_id == role_id)
        )
        user_ids = result.scalars().all()

    r = get_redis()
    keys = []
    for uid in user_ids:
        keys.append(f"{_PERMS_PREFIX}{uid}")
        keys.append(f"{_ROLE_PREFIX}{uid}")
    if keys:
        await r.delete(*keys)
