from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.services.auth import AuthService


def _permission(codename):
    return SimpleNamespace(codename=codename, id=1)


def _role(*, name="mentor", is_mentor=True, is_student=False, permissions=None):
    return SimpleNamespace(
        id=1,
        name=name,
        display_name="Ментор",
        is_mentor=is_mentor,
        is_student=is_student,
        permissions=permissions or [],
    )


def _user(*, role_rel=None):
    return SimpleNamespace(telegram_id=100, role_rel=role_rel)


@patch("src.services.auth.set_cached_permissions", new_callable=AsyncMock)
@patch("src.services.auth.get_cached_permissions", new_callable=AsyncMock)
@patch("src.services.auth.UserDAO")
class TestGetUserPermissions:
    async def test_cache_hit(self, mock_user_dao, mock_get_cache, mock_set_cache):
        mock_get_cache.return_value = {"view", "edit"}
        result = await AuthService.get_user_permissions(100)
        assert result == {"view", "edit"}
        mock_user_dao.find_one_or_none.assert_not_called()

    async def test_cache_miss_fetches_from_db(
        self, mock_user_dao, mock_get_cache, mock_set_cache
    ):
        mock_get_cache.return_value = None
        role = _role(permissions=[_permission("view"), _permission("edit")])
        mock_user_dao.find_one_or_none = AsyncMock(return_value=_user(role_rel=role))
        result = await AuthService.get_user_permissions(100)
        assert result == {"view", "edit"}
        mock_set_cache.assert_called_once()

    async def test_user_not_found(self, mock_user_dao, mock_get_cache, mock_set_cache):
        mock_get_cache.return_value = None
        mock_user_dao.find_one_or_none = AsyncMock(return_value=None)
        result = await AuthService.get_user_permissions(100)
        assert result == set()

    async def test_user_no_role(self, mock_user_dao, mock_get_cache, mock_set_cache):
        mock_get_cache.return_value = None
        mock_user_dao.find_one_or_none = AsyncMock(
            return_value=_user(role_rel=None)
        )
        result = await AuthService.get_user_permissions(100)
        assert result == set()

    @patch("src.services.auth.PermissionDAO")
    async def test_all_permissions_expansion(
        self, mock_perm_dao, mock_user_dao, mock_get_cache, mock_set_cache
    ):
        mock_get_cache.return_value = None
        role = _role(permissions=[_permission("all_permissions")])
        mock_user_dao.find_one_or_none = AsyncMock(return_value=_user(role_rel=role))
        mock_perm_dao.get_all = AsyncMock(
            return_value=[_permission("view"), _permission("edit"), _permission("admin")]
        )
        result = await AuthService.get_user_permissions(100)
        assert result == {"view", "edit", "admin"}


@patch("src.services.auth.set_cached_permissions", new_callable=AsyncMock)
@patch("src.services.auth.get_cached_permissions", new_callable=AsyncMock)
@patch("src.services.auth.UserDAO")
class TestHasPermission:
    async def test_has(self, mock_user_dao, mock_get_cache, mock_set_cache):
        mock_get_cache.return_value = {"view", "edit"}
        assert await AuthService.has_permission(100, "view") is True

    async def test_missing(self, mock_user_dao, mock_get_cache, mock_set_cache):
        mock_get_cache.return_value = {"view"}
        assert await AuthService.has_permission(100, "admin") is False


@patch("src.services.auth.set_cached_role", new_callable=AsyncMock)
@patch("src.services.auth.get_cached_role", new_callable=AsyncMock)
@patch("src.services.auth.UserDAO")
class TestGetUserRole:
    async def test_cache_hit(self, mock_user_dao, mock_get_role, mock_set_role):
        mock_get_role.return_value = {
            "id": 1,
            "name": "mentor",
            "display_name": "Ментор",
            "is_mentor": True,
            "is_student": False,
        }
        role = await AuthService.get_user_role(100)
        assert role is not None
        assert role.name == "mentor"
        mock_user_dao.find_one_or_none.assert_not_called()

    async def test_cache_miss(self, mock_user_dao, mock_get_role, mock_set_role):
        mock_get_role.return_value = None
        role_obj = _role()
        mock_user_dao.find_one_or_none = AsyncMock(
            return_value=_user(role_rel=role_obj)
        )
        role = await AuthService.get_user_role(100)
        assert role is role_obj
        mock_set_role.assert_called_once()

    async def test_user_not_found(self, mock_user_dao, mock_get_role, mock_set_role):
        mock_get_role.return_value = None
        mock_user_dao.find_one_or_none = AsyncMock(return_value=None)
        assert await AuthService.get_user_role(100) is None


class TestInvalidate:
    @patch("src.services.auth.invalidate_user_cache", new_callable=AsyncMock)
    async def test_invalidate_user(self, mock_invalidate):
        await AuthService.invalidate_user(100)
        mock_invalidate.assert_called_once_with(100)

    @patch("src.services.auth.invalidate_role_cache", new_callable=AsyncMock)
    async def test_invalidate_role(self, mock_invalidate):
        await AuthService.invalidate_role(1)
        mock_invalidate.assert_called_once_with(1)
