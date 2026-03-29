from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.models.user import User
from src.models.role import RoleModel, Permission, role_permissions

from src.core.database import async_session_maker


class UserDAO(BaseDAO):
    model = User

    @classmethod
    async def get_all(
        cls,
        *,
        role_name: str | None = None,
        registered_from: datetime | None = None,
        registered_to: datetime | None = None,
        **filter_by,
    ):
        async with async_session_maker() as session:
            query = select(cls.model).options(
                joinedload(cls.model.role_rel),
            )
            if filter_by:
                query = query.filter_by(**filter_by)
            if role_name is not None:
                query = query.join(RoleModel, cls.model.role_id == RoleModel.id).where(
                    RoleModel.name == role_name
                )
            if registered_from is not None:
                query = query.where(cls.model.registered_at >= registered_from)
            if registered_to is not None:
                query = query.where(cls.model.registered_at <= registered_to)
            result = await session.execute(query)
            result = result.unique()
            return result.scalars().all()

    @classmethod
    async def get_all_with_permission(cls, permission: str):
        async with async_session_maker() as session:
            query = (
                select(cls.model)
                .options(joinedload(cls.model.role_rel))
                .join(RoleModel, cls.model.role_id == RoleModel.id)
                .join(role_permissions, role_permissions.c.role_id == RoleModel.id)
                .join(
                    Permission,
                    Permission.id == role_permissions.c.permission_id,
                )
                .where(
                    Permission.codename == permission,
                    cls.model.is_placeholder.is_(False),
                )
            )
            result = await session.execute(query)
            result = result.unique()
            return result.scalars().all()

    @classmethod
    async def get_telegram_ids_by_role(cls, role_id: int) -> list[int]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(cls.model.telegram_id).where(cls.model.role_id == role_id)
            )
            return list(result.scalars().all())

    @classmethod
    async def update(cls, telegram_id: int, **values):
        async with async_session_maker() as session:
            query = (
                update(cls.model)
                .where(cls.model.telegram_id == telegram_id)
                .values(**values)
                .returning(cls.model)
            )
            result = await session.execute(query)
            await session.commit()
            return result.scalars().first()
