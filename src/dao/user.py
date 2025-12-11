from sqlalchemy import select, insert, delete, update
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.models.user import User

from src.core.database import async_session_maker


class UserDAO(BaseDAO):
    model = User

    @classmethod
    async def get_all(cls, **filter_by):
        async with async_session_maker() as session:
            query = (
                select(cls.model)
                .filter_by(**filter_by)
                .options(
                    joinedload(cls.model.cohort),
                    joinedload(cls.model.mentor),
                    joinedload(cls.model.meetings)
                )
            )
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
