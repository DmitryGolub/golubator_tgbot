from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.dao.role import PermissionDAO, RoleDAO
from src.dao.user import UserDAO
from src.models.role import RoleModel
from src.models.user import User
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
            },
        )
        return role

    @staticmethod
    async def invalidate_user(user_id: int) -> None:
        await invalidate_user_cache(user_id)

    @staticmethod
    async def invalidate_role(role_id: int) -> None:
        await invalidate_role_cache(role_id)

    @staticmethod
    async def ensure_user(tg_user) -> User:
        """Create or sync User record from Telegram user object. Returns User."""
        real_id = tg_user.id
        existing = await UserDAO.find_one_or_none(telegram_id=real_id)

        if existing:
            updates: dict = {}
            if existing.registered_at is None:
                updates["registered_at"] = datetime.now(timezone.utc)
            if existing.username != tg_user.username:
                updates["username"] = tg_user.username
            if updates:
                await UserDAO.update(telegram_id=real_id, **updates)
            return existing

        is_admin = real_id in settings.admin_ids
        role_obj = await RoleDAO.get_by_name("admin" if is_admin else "student")
        try:
            return await UserDAO.add(
                telegram_id=real_id,
                username=tg_user.username,
                name=tg_user.full_name,
                role_id=role_obj.id if role_obj else None,
                registered_at=datetime.now(timezone.utc),
            )
        except IntegrityError:
            # Race condition: another concurrent /start created the user simultaneously
            existing = await UserDAO.find_one_or_none(telegram_id=real_id)
            if existing:
                return existing
            raise
