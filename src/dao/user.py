from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.models.user import User

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
                from src.models.role import RoleModel

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
