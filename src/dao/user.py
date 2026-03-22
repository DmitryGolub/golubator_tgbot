from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload, selectinload

from src.core.dao import BaseDAO
from src.models.tag import Tag
from src.models.user import User, State

from src.core.database import async_session_maker


class UserDAO(BaseDAO):
    model = User

    @classmethod
    async def get_all(
        cls,
        *,
        role_name: str | None = None,
        state: State | None = None,
        tag_id: int | None = None,
        registered_from: datetime | None = None,
        registered_to: datetime | None = None,
        **filter_by,
    ):
        async with async_session_maker() as session:
            query = (
                select(cls.model)
                .options(
                    joinedload(cls.model.cohort),
                    joinedload(cls.model.mentor),
                    joinedload(cls.model.meetings),
                    joinedload(cls.model.role_rel),
                    selectinload(cls.model.tags),
                )
            )
            if filter_by:
                query = query.filter_by(**filter_by)
            if role_name is not None:
                from src.models.role import RoleModel
                query = query.join(RoleModel, cls.model.role_id == RoleModel.id).where(RoleModel.name == role_name)
            if state is not None:
                query = query.where(cls.model.state == state)
            if tag_id is not None:
                query = query.join(cls.model.tags).where(Tag.id == tag_id)
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

    @classmethod
    async def assign_tag(cls, telegram_id: int, tag_id: int) -> User | None:
        async with async_session_maker() as session:
            user = await session.scalar(
                select(cls.model)
                .where(cls.model.telegram_id == telegram_id)
                .options(selectinload(cls.model.tags))
            )
            if not user:
                return None

            tag = await session.scalar(select(Tag).where(Tag.id == tag_id))
            if not tag:
                return None

            if all(existing_tag.id != tag.id for existing_tag in user.tags):
                user.tags.append(tag)
                await session.commit()

            return user

    @classmethod
    async def unassign_tag(cls, telegram_id: int, tag_id: int) -> User | None:
        async with async_session_maker() as session:
            user = await session.scalar(
                select(cls.model)
                .where(cls.model.telegram_id == telegram_id)
                .options(selectinload(cls.model.tags))
            )
            if not user:
                return None

            tag_to_remove = next((tag for tag in user.tags if tag.id == tag_id), None)
            if tag_to_remove:
                user.tags.remove(tag_to_remove)
                await session.commit()

            return user
