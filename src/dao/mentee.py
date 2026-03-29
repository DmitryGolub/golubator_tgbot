from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.mentee import Mentee
from src.models.mentor import Mentor


class MenteeDAO(BaseDAO):
    model = Mentee

    @classmethod
    async def find_by_telegram_id(cls, telegram_id: int) -> Mentee | None:
        async with async_session_maker() as session:
            query = select(cls.model).where(cls.model.telegram_id == telegram_id)
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def find_by_notion_page_id(cls, notion_page_id: str) -> Mentee | None:
        async with async_session_maker() as session:
            query = select(cls.model).where(cls.model.notion_page_id == notion_page_id)
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def get_by_mentor_id(cls, mentor_id: int) -> list[Mentee]:
        async with async_session_maker() as session:
            query = select(cls.model).where(cls.model.mentor_id == mentor_id)
            result = await session.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def get_by_mentor_telegram_id(cls, mentor_telegram_id: int) -> list[Mentee]:
        async with async_session_maker() as session:
            query = (
                select(cls.model)
                .join(Mentor, cls.model.mentor_id == Mentor.id)
                .where(Mentor.telegram_id == mentor_telegram_id)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def get_by_telegram_ids(cls, telegram_ids: list[int]) -> list[Mentee]:
        """Load mentees with mentor and user relations in a single query."""
        if not telegram_ids:
            return []
        async with async_session_maker() as session:
            query = (
                select(cls.model)
                .options(joinedload(cls.model.mentor), joinedload(cls.model.user))
                .where(cls.model.telegram_id.in_(telegram_ids))
            )
            result = await session.execute(query)
            return list(result.unique().scalars().all())

    @classmethod
    async def get_all_with_details(cls, **filter_by) -> list[Mentee]:
        async with async_session_maker() as session:
            query = select(cls.model).options(
                joinedload(cls.model.user),
                joinedload(cls.model.mentor),
            )
            if filter_by:
                query = query.filter_by(**filter_by)
            result = await session.execute(query)
            result = result.unique()
            return list(result.scalars().all())
