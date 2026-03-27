from datetime import datetime, timezone

from sqlalchemy import delete, distinct, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.database import async_session_maker
from src.models.cohort import Cohort, UserCohort
from src.models.mentee import Mentee


class CohortDAO:
    @staticmethod
    async def get_telegram_ids_in_cohort(
        cohort_type: str, cohort_value: str
    ) -> list[int]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Mentee.telegram_id)
                .join(UserCohort, UserCohort.mentee_id == Mentee.id)
                .join(Cohort, Cohort.id == UserCohort.cohort_id)
                .where(
                    Cohort.type == cohort_type,
                    Cohort.value == cohort_value,
                    Mentee.telegram_id.isnot(None),
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_mentee_cohorts(mentee_id: int) -> list[UserCohort]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(UserCohort).where(UserCohort.mentee_id == mentee_id)
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_cohorts_batch(
        mentee_ids: list[int],
    ) -> dict[int, list[UserCohort]]:
        if not mentee_ids:
            return {}
        async with async_session_maker() as session:
            result = await session.execute(
                select(UserCohort).where(UserCohort.mentee_id.in_(mentee_ids))
            )
            rows = result.scalars().all()
            mapping: dict[int, list[UserCohort]] = {}
            for uc in rows:
                mapping.setdefault(uc.mentee_id, []).append(uc)
            return mapping

    @staticmethod
    async def get_distinct_types() -> list[str]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(distinct(Cohort.type)).order_by(Cohort.type)
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_distinct_values(cohort_type: str) -> list[str]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(distinct(Cohort.value))
                .where(Cohort.type == cohort_type)
                .order_by(Cohort.value)
            )
            return list(result.scalars().all())

    @staticmethod
    async def replace_mentee_cohorts(
        mentee_id: int, memberships: list[tuple[str, str]]
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(UserCohort).where(UserCohort.mentee_id == mentee_id)
            )
            now = datetime.now(timezone.utc)
            for cohort_type, cohort_value in memberships:
                await session.execute(
                    pg_insert(Cohort)
                    .values(type=cohort_type, value=cohort_value)
                    .on_conflict_do_nothing(constraint="uq_cohort_type_value")
                )
                result = await session.execute(
                    select(Cohort.id).where(
                        Cohort.type == cohort_type, Cohort.value == cohort_value
                    )
                )
                cohort_id = result.scalar_one()
                session.add(
                    UserCohort(
                        mentee_id=mentee_id,
                        cohort_id=cohort_id,
                        synced_at=now,
                    )
                )
            await session.commit()

    @staticmethod
    async def update_mentee_cohort_by_type(
        mentee_id: int, cohort_type: str, cohort_value: str
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(UserCohort).where(
                    UserCohort.mentee_id == mentee_id,
                    UserCohort.cohort_id.in_(
                        select(Cohort.id).where(Cohort.type == cohort_type)
                    ),
                )
            )
            now = datetime.now(timezone.utc)
            await session.execute(
                pg_insert(Cohort)
                .values(type=cohort_type, value=cohort_value)
                .on_conflict_do_nothing(constraint="uq_cohort_type_value")
            )
            result = await session.execute(
                select(Cohort.id).where(
                    Cohort.type == cohort_type, Cohort.value == cohort_value
                )
            )
            cohort_id = result.scalar_one()
            session.add(
                UserCohort(mentee_id=mentee_id, cohort_id=cohort_id, synced_at=now)
            )
            await session.execute(
                update(Mentee).where(Mentee.id == mentee_id).values(updated_at=now)
            )
            await session.commit()
