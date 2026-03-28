from datetime import datetime, timezone

from sqlalchemy import delete, distinct, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.database import async_session_maker
from src.models.cohort import Cohort, UserCohort
from src.models.user import User


class CohortDAO:
    @staticmethod
    async def get_telegram_ids_in_cohort(
        cohort_type: str, cohort_value: str
    ) -> list[int]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(UserCohort.user_telegram_id)
                .join(Cohort, Cohort.id == UserCohort.cohort_id)
                .where(
                    Cohort.type == cohort_type,
                    Cohort.value == cohort_value,
                    UserCohort.user_telegram_id > 0,
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_user_cohorts(user_telegram_id: int) -> list[UserCohort]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(UserCohort).where(
                    UserCohort.user_telegram_id == user_telegram_id
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_cohorts_batch(
        user_telegram_ids: list[int],
    ) -> dict[int, list[UserCohort]]:
        if not user_telegram_ids:
            return {}
        async with async_session_maker() as session:
            result = await session.execute(
                select(UserCohort).where(
                    UserCohort.user_telegram_id.in_(user_telegram_ids)
                )
            )
            rows = result.scalars().all()
            mapping: dict[int, list[UserCohort]] = {}
            for uc in rows:
                mapping.setdefault(uc.user_telegram_id, []).append(uc)
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
    async def replace_user_cohorts(
        user_telegram_id: int, memberships: list[tuple[str, str]]
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(UserCohort).where(
                    UserCohort.user_telegram_id == user_telegram_id
                )
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
                        user_telegram_id=user_telegram_id,
                        cohort_id=cohort_id,
                        synced_at=now,
                    )
                )
            await session.commit()

    @staticmethod
    async def update_user_cohort_by_type(
        user_telegram_id: int, cohort_type: str, cohort_value: str
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(UserCohort).where(
                    UserCohort.user_telegram_id == user_telegram_id,
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
                UserCohort(
                    user_telegram_id=user_telegram_id,
                    cohort_id=cohort_id,
                    synced_at=now,
                )
            )
            await session.execute(
                update(User)
                .where(User.telegram_id == user_telegram_id)
                .values(updated_at=now)
            )
            await session.commit()
