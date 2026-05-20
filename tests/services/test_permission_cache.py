from unittest.mock import AsyncMock, patch

from src.services.permission_cache import (
    get_cached_permissions,
    get_cached_role,
    invalidate_user_cache,
    set_cached_permissions,
    set_cached_role,
)


def _mock_redis():
    store = {}
    r = AsyncMock()
    r.get = AsyncMock(side_effect=lambda k: store.get(k))
    r.set = AsyncMock(side_effect=lambda k, v, **kw: store.__setitem__(k, v))
    r.delete = AsyncMock(
        side_effect=lambda *keys: sum(1 for k in keys if store.pop(k, None) is not None)
    )
    return r, store


@patch("src.services.permission_cache.get_redis")
class TestPermissionCache:
    async def test_get_miss(self, mock_get_redis):
        r, _ = _mock_redis()
        mock_get_redis.return_value = r
        assert await get_cached_permissions(100) is None

    async def test_set_and_get(self, mock_get_redis):
        r, store = _mock_redis()
        mock_get_redis.return_value = r

        await set_cached_permissions(100, {"view", "edit"})
        result = await get_cached_permissions(100)
        assert result == {"view", "edit"}

    async def test_role_miss(self, mock_get_redis):
        r, _ = _mock_redis()
        mock_get_redis.return_value = r
        assert await get_cached_role(100) is None

    async def test_role_set_and_get(self, mock_get_redis):
        r, store = _mock_redis()
        mock_get_redis.return_value = r

        data = {"id": 1, "name": "mentor", "display_name": "M"}
        await set_cached_role(100, data)
        result = await get_cached_role(100)
        assert result == data

    async def test_invalidate_user(self, mock_get_redis):
        r, store = _mock_redis()
        mock_get_redis.return_value = r

        await set_cached_permissions(100, {"view"})
        await set_cached_role(
            100,
            {
                "id": 1,
                "name": "m",
                "display_name": "M",
            },
        )

        assert await get_cached_permissions(100) is not None
        await invalidate_user_cache(100)
        assert await get_cached_permissions(100) is None
        assert await get_cached_role(100) is None
