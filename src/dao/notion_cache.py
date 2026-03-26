from sqlalchemy import delete, select, distinct

from src.core.database import async_session_maker
from src.models.mentee import Mentee
from src.models.notion_cache import NotionCohortCache


class NotionCacheDAO:
    @staticmethod
    async def get_users_in_cohort(cohort_type: str, cohort_value: str) -> list[int]:
        """Return telegram_ids of mentees matching a cohort filter."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Mentee.telegram_id)
                .join(NotionCohortCache, NotionCohortCache.mentee_id == Mentee.id)
                .where(
                    NotionCohortCache.cohort_type == cohort_type,
                    NotionCohortCache.cohort_value == cohort_value,
                    Mentee.telegram_id.isnot(None),
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_user_cohorts(telegram_id: int) -> list[NotionCohortCache]:
        """Return cohort records for a mentee identified by telegram_id."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotionCohortCache)
                .join(Mentee, NotionCohortCache.mentee_id == Mentee.id)
                .where(Mentee.telegram_id == telegram_id)
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_cohorts_batch(
        user_ids: list[int],
    ) -> dict[int, list[NotionCohortCache]]:
        """Load cohorts for multiple mentees (by telegram_id) in one query."""
        if not user_ids:
            return {}
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotionCohortCache, Mentee.telegram_id)
                .join(Mentee, NotionCohortCache.mentee_id == Mentee.id)
                .where(Mentee.telegram_id.in_(user_ids))
            )
            rows = result.all()
            mapping: dict[int, list[NotionCohortCache]] = {}
            for cache_row, tid in rows:
                mapping.setdefault(tid, []).append(cache_row)
            return mapping

    @staticmethod
    async def get_distinct_types() -> list[str]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(distinct(NotionCohortCache.cohort_type)).order_by(
                    NotionCohortCache.cohort_type
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_distinct_values(cohort_type: str) -> list[str]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(distinct(NotionCohortCache.cohort_value))
                .where(NotionCohortCache.cohort_type == cohort_type)
                .order_by(NotionCohortCache.cohort_value)
            )
            return list(result.scalars().all())

    @staticmethod
    async def replace_mentee_cohorts(
        mentee_id: int, memberships: list[tuple[str, str]]
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(NotionCohortCache).where(
                    NotionCohortCache.mentee_id == mentee_id
                )
            )
            for cohort_type, cohort_value in memberships:
                session.add(
                    NotionCohortCache(
                        mentee_id=mentee_id,
                        cohort_type=cohort_type,
                        cohort_value=cohort_value,
                    )
                )
            await session.commit()
