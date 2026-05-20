from sqlalchemy import select, update

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.ui_text import UiText


class UiTextDAO(BaseDAO):
    model = UiText

    @classmethod
    async def get_by_key(cls, key: str) -> UiText | None:
        async with async_session_maker() as session:
            result = await session.execute(select(UiText).where(UiText.key == key))
            return result.scalars().one_or_none()

    @classmethod
    async def get_many(cls, keys: list[str]) -> dict[str, str]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(UiText.key, UiText.value).where(UiText.key.in_(keys))
            )
            return dict(result.all())

    @classmethod
    async def update_value(cls, key: str, value: str) -> UiText | None:
        async with async_session_maker() as session:
            result = await session.execute(
                update(UiText)
                .where(UiText.key == key)
                .values(value=value)
                .returning(UiText)
            )
            await session.commit()
            return result.scalars().first()
