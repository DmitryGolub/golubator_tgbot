from sqlalchemy import delete, select, distinct

from src.core.database import async_session_maker
from src.models.notion_cache import NotionCohortCache


class NotionCacheDAO:
    @staticmethod
    async def get_users_in_cohort(cohort_type: str, cohort_value: str) -> list[int]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotionCohortCache.user_telegram_id).where(
                    NotionCohortCache.cohort_type == cohort_type,
                    NotionCohortCache.cohort_value == cohort_value,
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_user_cohorts(telegram_id: int) -> list[NotionCohortCache]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotionCohortCache).where(
                    NotionCohortCache.user_telegram_id == telegram_id
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_cohorts_batch(
        user_ids: list[int],
    ) -> dict[int, list["NotionCohortCache"]]:
        """Load cohorts for multiple users in one query."""
        if not user_ids:
            return {}
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotionCohortCache).where(
                    NotionCohortCache.user_telegram_id.in_(user_ids)
                )
            )
            rows = result.scalars().all()
            mapping: dict[int, list[NotionCohortCache]] = {}
            for row in rows:
                mapping.setdefault(row.user_telegram_id, []).append(row)
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
    async def replace_user_cohorts(
        telegram_id: int, memberships: list[tuple[str, str]]
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(NotionCohortCache).where(
                    NotionCohortCache.user_telegram_id == telegram_id
                )
            )
            for cohort_type, cohort_value in memberships:
                session.add(
                    NotionCohortCache(
                        user_telegram_id=telegram_id,
                        cohort_type=cohort_type,
                        cohort_value=cohort_value,
                    )
                )
            await session.commit()
