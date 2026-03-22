from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.bot.filters.role import RoleFilter


def _event(user_id=100):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id))


def _event_no_user():
    return SimpleNamespace(from_user=None)


@patch("src.bot.filters.role.AuthService")
class TestRoleFilter:
    async def test_match(self, mock_auth):
        mock_auth.get_user_role = AsyncMock(
            return_value=SimpleNamespace(name="mentor")
        )
        f = RoleFilter(["mentor", "admin"])
        assert await f(_event()) is True

    async def test_no_match(self, mock_auth):
        mock_auth.get_user_role = AsyncMock(
            return_value=SimpleNamespace(name="student")
        )
        f = RoleFilter(["mentor"])
        assert await f(_event()) is False

    async def test_role_none(self, mock_auth):
        mock_auth.get_user_role = AsyncMock(return_value=None)
        f = RoleFilter(["mentor"])
        assert await f(_event()) is False

    async def test_no_user(self, mock_auth):
        f = RoleFilter(["mentor"])
        assert await f(_event_no_user()) is False
