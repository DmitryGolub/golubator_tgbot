from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.mentor import Mentor


class MentorDAO(BaseDAO):
    model = Mentor

    @classmethod
    async def find_by_telegram_id(cls, telegram_id: int) -> Mentor | None:
        async with async_session_maker() as session:
            query = select(cls.model).where(cls.model.telegram_id == telegram_id)
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def find_by_notion_page_id(cls, notion_page_id: str) -> Mentor | None:
        async with async_session_maker() as session:
            query = select(cls.model).where(cls.model.notion_page_id == notion_page_id)
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def get_all_with_users(cls) -> list[Mentor]:
        async with async_session_maker() as session:
            query = select(cls.model).options(joinedload(cls.model.user))
            result = await session.execute(query)
            return list(result.scalars().all())
