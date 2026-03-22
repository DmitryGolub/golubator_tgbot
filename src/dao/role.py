from sqlalchemy import select, delete as sa_delete, insert

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.role import Permission, RoleModel, role_permissions


class RoleDAO(BaseDAO):
    model = RoleModel

    @classmethod
    async def get_by_name(cls, name: str) -> RoleModel | None:
        async with async_session_maker() as session:
            query = select(cls.model).where(cls.model.name == name)
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def get_with_permissions(cls, role_id: int) -> RoleModel | None:
        async with async_session_maker() as session:
            query = select(cls.model).where(cls.model.id == role_id)
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def add_permission(cls, role_id: int, permission_id: int) -> None:
        async with async_session_maker() as session:
            await session.execute(
                insert(role_permissions).values(
                    role_id=role_id, permission_id=permission_id
                )
            )
            await session.commit()

    @classmethod
    async def remove_permission(cls, role_id: int, permission_id: int) -> None:
        async with async_session_maker() as session:
            await session.execute(
                sa_delete(role_permissions).where(
                    role_permissions.c.role_id == role_id,
                    role_permissions.c.permission_id == permission_id,
                )
            )
            await session.commit()

    @classmethod
    async def count_users(cls, role_id: int) -> int:
        from src.models.user import User
        from sqlalchemy import func

        async with async_session_maker() as session:
            query = (
                select(func.count()).select_from(User).where(User.role_id == role_id)
            )
            result = await session.execute(query)
            return result.scalar() or 0


class PermissionDAO(BaseDAO):
    model = Permission

    @classmethod
    async def get_by_codename(cls, codename: str) -> Permission | None:
        async with async_session_maker() as session:
            query = select(cls.model).where(cls.model.codename == codename)
            result = await session.execute(query)
            return result.scalars().one_or_none()
