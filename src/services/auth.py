from src.dao.role import PermissionDAO
from src.dao.user import UserDAO
from src.models.role import RoleModel
from src.services.permission_cache import (
    get_cached_permissions,
    get_cached_role,
    invalidate_role_cache,
    invalidate_user_cache,
    set_cached_permissions,
    set_cached_role,
)

ALL_PERMISSIONS = "all_permissions"


class AuthService:
    @staticmethod
    async def get_user_permissions(user_id: int) -> set[str]:
        cached = await get_cached_permissions(user_id)
        if cached is not None:
            return cached

        user = await UserDAO.find_one_or_none(telegram_id=user_id)
        if not user or not user.role_rel:
            return set()

        role = user.role_rel
        codenames = {p.codename for p in role.permissions}

        if ALL_PERMISSIONS in codenames:
            all_perms = await PermissionDAO.get_all()
            codenames = {p.codename for p in all_perms}

        await set_cached_permissions(user_id, codenames)
        return codenames

    @staticmethod
    async def has_permission(user_id: int, permission: str) -> bool:
        perms = await AuthService.get_user_permissions(user_id)
        return permission in perms

    @staticmethod
    async def get_user_role(user_id: int) -> RoleModel | None:
        cached = await get_cached_role(user_id)
        if cached is not None:
            role = RoleModel()
            role.id = cached["id"]
            role.name = cached["name"]
            role.display_name = cached["display_name"]
            role.is_mentor = cached["is_mentor"]
            role.is_student = cached["is_student"]
            return role

        user = await UserDAO.find_one_or_none(telegram_id=user_id)
        if not user or not user.role_rel:
            return None

        role = user.role_rel
        await set_cached_role(
            user_id,
            {
                "id": role.id,
                "name": role.name,
                "display_name": role.display_name,
                "is_mentor": role.is_mentor,
                "is_student": role.is_student,
            },
        )
        return role

    @staticmethod
    async def invalidate_user(user_id: int) -> None:
        await invalidate_user_cache(user_id)

    @staticmethod
    async def invalidate_role(role_id: int) -> None:
        await invalidate_role_cache(role_id)
