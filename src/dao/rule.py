from typing import Iterable

from sqlalchemy import insert, select
from sqlalchemy.orm import joinedload

from src.core.database import async_session_maker
from src.models.rule import UserRule, StateRule, CohortRule, Regularity
from src.models.user import State


class RuleDAO:
    @staticmethod
    async def create_user_rules(
        *,
        user_ids: Iterable[int],
        name: str | None,
        text: str,
        regularity: Regularity,
        author_id: int,
    ) -> list[UserRule]:
        async with async_session_maker() as session:
            values = [
                {
                    "user_id": uid,
                    "name": name,
                    "text": text,
                    "regularity": regularity,
                    "author_id": author_id,
                }
                for uid in user_ids
            ]
            stmt = insert(UserRule).values(values).returning(UserRule)
            res = await session.execute(stmt)
            await session.commit()
            return list(res.scalars().all())

    @staticmethod
    async def create_state_rules(
        *,
        states: Iterable[State],
        name: str | None,
        text: str,
        regularity: Regularity,
        author_id: int,
        offset_days: int | None,
    ) -> list[StateRule]:
        async with async_session_maker() as session:
            values = [
                {
                    "user_state": state,
                    "name": name,
                    "text": text,
                    "regularity": regularity,
                    "author_id": author_id,
                    "offset_days": offset_days,
                }
                for state in states
            ]
            stmt = insert(StateRule).values(values).returning(StateRule)
            res = await session.execute(stmt)
            await session.commit()
            return list(res.scalars().all())

    @staticmethod
    async def list_user_rules() -> list[UserRule]:
        async with async_session_maker() as session:
            query = (
                select(UserRule)
                .options(joinedload(UserRule.user))
                .options(joinedload(UserRule.author))
                .order_by(UserRule.id.desc())
            )
            res = await session.execute(query)
            res = res.unique()
            return list(res.scalars().all())

    @staticmethod
    async def delete_user_rules(ids: Iterable[int]) -> None:
        async with async_session_maker() as session:
            await session.execute(UserRule.__table__.delete().where(UserRule.id.in_(list(ids))))
            await session.commit()

    @staticmethod
    async def delete_state_rules(ids: Iterable[int]) -> None:
        async with async_session_maker() as session:
            await session.execute(StateRule.__table__.delete().where(StateRule.id.in_(list(ids))))
            await session.commit()

    @staticmethod
    async def list_state_rules() -> list[StateRule]:
        async with async_session_maker() as session:
            query = (
                select(StateRule)
                .options(joinedload(StateRule.author))
                .order_by(StateRule.id.desc())
            )
            res = await session.execute(query)
            res = res.unique()
            return list(res.scalars().all())

    # Cohort rules
    @staticmethod
    async def create_cohort_rules(
        *,
        cohort_ids: Iterable[int],
        name: str | None,
        text: str,
        regularity: Regularity,
        author_id: int,
    ) -> list[CohortRule]:
        async with async_session_maker() as session:
            values = [
                {
                    "cohort_id": cid,
                    "name": name,
                    "text": text,
                    "regularity": regularity,
                    "author_id": author_id,
                }
                for cid in cohort_ids
            ]
            stmt = insert(CohortRule).values(values).returning(CohortRule)
            res = await session.execute(stmt)
            await session.commit()
            return list(res.scalars().all())

    @staticmethod
    async def list_cohort_rules() -> list[CohortRule]:
        async with async_session_maker() as session:
            query = (
                select(CohortRule)
                .options(joinedload(CohortRule.author))
                .options(joinedload(CohortRule.cohort))
                .order_by(CohortRule.id.desc())
            )
            res = await session.execute(query)
            res = res.unique()
            return list(res.scalars().all())

    @staticmethod
    async def delete_cohort_rules(ids: Iterable[int]) -> None:
        async with async_session_maker() as session:
            await session.execute(CohortRule.__table__.delete().where(CohortRule.id.in_(list(ids))))
            await session.commit()
