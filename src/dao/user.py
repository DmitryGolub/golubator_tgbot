from sqlalchemy import select, insert, delete, update
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.models.user import User

from src.core.database import async_session_maker


class UserDAO(BaseDAO):
    model = User

    @classmethod
    async def get_all(cls):
        async with async_session_maker() as session:
            query = (
                select(cls.model)
                .options(
                    joinedload(cls.model.cohort),
                    joinedload(cls.model.mentor),
                    joinedload(cls.model.meetings)
                )
            )
            result = await session.execute(query)
            result = result.unique()
            return result.scalars().all()
