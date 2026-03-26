import logging

from sqlalchemy import inspect as sa_inspect, select, insert, delete, update

from src.core.database import async_session_maker

logger = logging.getLogger(__name__)


class BaseDAO:
    model = None

    @classmethod
    def _pk_column(cls):
        mapper = sa_inspect(cls.model)
        return mapper.primary_key[0]

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
                "%s.add -> pk=%s",
                cls.model.__name__,
                getattr(obj, cls._pk_column().key, "?"),
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
    async def update(cls, pk_value, **values):
        pk_col = cls._pk_column()
        async with async_session_maker() as session:
            query = (
                update(cls.model)
                .where(pk_col == pk_value)
                .values(**values)
                .returning(cls.model)
            )
            result = await session.execute(query)
            await session.commit()
            obj = result.scalars().first()
            logger.debug("%s.update(pk=%s)", cls.model.__name__, pk_value)
            return obj
