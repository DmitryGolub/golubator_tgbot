import logging

from sqlalchemy import select, insert, delete, update

from src.core.database import async_session_maker

logger = logging.getLogger(__name__)


class BaseDAO:
    model = None

    @classmethod
    async def get_all(cls):
        async with async_session_maker() as session:
            query = select(cls.model)
            result = await session.execute(query)
            return result.scalars().all()

    @classmethod
    async def find_one_or_none(cls, **filter_by):
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(**filter_by)
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def add(cls, **data):
        async with async_session_maker() as session:
            query = insert(cls.model).values(**data).returning(cls.model)
            result = await session.execute(query)
            await session.commit()
            obj = result.scalars().first()
            logger.debug(
                "%s.add -> id=%s", cls.model.__name__, getattr(obj, "id", "?")
            )
            return obj

    @classmethod
    async def delete(cls, **filter_by):
        async with async_session_maker() as session:
            query = delete(cls.model).filter_by(**filter_by)
            await session.execute(query)
            await session.commit()
            logger.debug("%s.delete(%s)", cls.model.__name__, filter_by)

    @classmethod
    async def update(cls, id: int, **values):
        async with async_session_maker() as session:
            query = (
                update(cls.model)
                .where(cls.model.id == id)
                .values(**values)
                .returning(cls.model)
            )
            result = await session.execute(query)
            await session.commit()
            obj = result.scalars().first()
            logger.debug("%s.update(id=%s)", cls.model.__name__, id)
            return obj
