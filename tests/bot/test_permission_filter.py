from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.bot.filters.permission import PermissionFilter


def _event(user_id=100):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id))


def _event_no_user():
    return SimpleNamespace(from_user=None)


@patch("src.bot.filters.permission.AuthService")
class TestPermissionFilter:
    async def test_match(self, mock_auth):
        mock_auth.get_user_permissions = AsyncMock(
            return_value={"view", "edit"}
        )
        f = PermissionFilter("view")
        assert await f(_event()) is True

    async def test_no_match(self, mock_auth):
        mock_auth.get_user_permissions = AsyncMock(return_value={"view"})
        f = PermissionFilter("admin")
        assert await f(_event()) is False

    async def test_multiple_required_any_match(self, mock_auth):
        mock_auth.get_user_permissions = AsyncMock(
            return_value={"edit"}
        )
        f = PermissionFilter(["view", "edit"])
        assert await f(_event()) is True

    async def test_no_user(self, mock_auth):
        f = PermissionFilter("view")
        assert await f(_event_no_user()) is False
