from datetime import datetime

from sqlalchemy import or_, func, select, update
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
    async def get_paginated(
        cls,
        *,
        page: int = 0,
        page_size: int = 6,
        role_name: str | None = None,
        search: str | None = None,
        exclude_placeholders: bool = False,
        **filter_by,
    ) -> tuple[list[User], int]:
        async with async_session_maker() as session:
            base = select(cls.model).options(joinedload(cls.model.role_rel))
            if filter_by:
                base = base.filter_by(**filter_by)
            if role_name is not None:
                base = base.join(RoleModel, cls.model.role_id == RoleModel.id).where(
                    RoleModel.name == role_name
                )
            if exclude_placeholders:
                base = base.where(cls.model.telegram_id > 0)
            if search:
                pattern = f"%{search}%"
                base = base.where(
                    or_(
                        cls.model.name.ilike(pattern),
                        cls.model.username.ilike(pattern),
                    )
                )

            count_result = await session.execute(
                select(func.count()).select_from(base.subquery())
            )
            total = count_result.scalar_one()

            query = (
                base.order_by(cls.model.telegram_id)
                .offset(page * page_size)
                .limit(page_size)
            )
            result = await session.execute(query)
            users = list(result.unique().scalars().all())
            total_pages = max(1, (total + page_size - 1) // page_size)
            return users, total_pages

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
                    or_(
                        Permission.codename == permission,
                        Permission.codename == "all_permissions",
                    ),
                    cls.model.telegram_id > 0,
                )
            )
            result = await session.execute(query)
            result = result.unique()
            return result.scalars().all()

    @classmethod
    async def get_telegram_ids_by_role(cls, role_id: int) -> list[int]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(cls.model.telegram_id).where(
                    cls.model.role_id == role_id,
                    cls.model.telegram_id > 0,
                )
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
