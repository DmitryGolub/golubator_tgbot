from datetime import datetime, timezone

from sqlalchemy import delete, distinct, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.database import async_session_maker
from src.models.cohort import Cohort, UserCohort
from src.models.role import Permission, RoleModel, role_permissions
from src.models.mentee import Mentee
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
    async def get_direction_leads_for_student(
        student_telegram_id: int,
    ) -> list[int]:
        async with async_session_maker() as session:
            student_categories = (
                select(Cohort.id)
                .join(UserCohort, UserCohort.cohort_id == Cohort.id)
                .where(
                    UserCohort.user_telegram_id == student_telegram_id,
                    Cohort.type == "Category",
                )
            )
            result = await session.execute(
                select(UserCohort.user_telegram_id)
                .join(Cohort, Cohort.id == UserCohort.cohort_id)
                .join(User, User.telegram_id == UserCohort.user_telegram_id)
                .join(RoleModel, RoleModel.id == User.role_id)
                .join(role_permissions, role_permissions.c.role_id == RoleModel.id)
                .join(
                    Permission,
                    Permission.id == role_permissions.c.permission_id,
                )
                .where(
                    UserCohort.cohort_id.in_(student_categories),
                    Permission.codename == "receive_direction_notifications",
                    UserCohort.user_telegram_id != student_telegram_id,
                    User.is_placeholder.is_(False),
                )
                .distinct()
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_students_for_direction_lead(
        lead_telegram_id: int,
    ) -> dict[str, list[tuple[User, str | None]]]:
        """Return {direction_name: [(User, doc_name), ...]} for Category cohorts the lead belongs to."""
        async with async_session_maker() as session:
            lead_cohorts = (
                select(Cohort.id, Cohort.value)
                .join(UserCohort, UserCohort.cohort_id == Cohort.id)
                .where(
                    UserCohort.user_telegram_id == lead_telegram_id,
                    Cohort.type == "Category",
                )
                .subquery()
            )

            result = await session.execute(
                select(lead_cohorts.c.value, User, Mentee.doc_name)
                .join(UserCohort, UserCohort.cohort_id == lead_cohorts.c.id)
                .join(User, User.telegram_id == UserCohort.user_telegram_id)
                .outerjoin(Mentee, Mentee.telegram_id == User.telegram_id)
                .where(
                    UserCohort.user_telegram_id != lead_telegram_id,
                )
                .order_by(lead_cohorts.c.value, User.name)
            )

            grouped: dict[str, list[tuple[User, str | None]]] = {}
            for direction, user, doc_name in result.tuples().all():
                grouped.setdefault(direction, []).append((user, doc_name))
            return grouped

    @staticmethod
    async def get_types_with_value_counts() -> list[tuple[str, int]]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Cohort.type, func.count(Cohort.id))
                .group_by(Cohort.type)
                .order_by(Cohort.type)
            )
            return list(result.tuples().all())

    @staticmethod
    async def get_user_cohort_values_by_type(
        user_telegram_id: int, cohort_type: str
    ) -> list[str]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Cohort.value)
                .join(UserCohort, UserCohort.cohort_id == Cohort.id)
                .where(
                    UserCohort.user_telegram_id == user_telegram_id,
                    Cohort.type == cohort_type,
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def update_user_cohort_by_type(
        user_telegram_id: int, cohort_type: str, cohort_value: str
    ) -> tuple[str | None, str]:
        """Update user cohort and return (old_value, new_value)."""
        async with async_session_maker() as session:
            async with session.begin():
                old_result = await session.execute(
                    select(Cohort.value)
                    .join(UserCohort, UserCohort.cohort_id == Cohort.id)
                    .where(
                        UserCohort.user_telegram_id == user_telegram_id,
                        Cohort.type == cohort_type,
                    )
                )
                old_value = old_result.scalar_one_or_none()

                if old_value == cohort_value:
                    return old_value, cohort_value

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
                from src.models.stage_transition import StageTransition

                session.add(
                    StageTransition(
                        user_telegram_id=user_telegram_id,
                        cohort_type=cohort_type,
                        old_value=old_value,
                        new_value=cohort_value,
                        source="bot",
                    )
                )
            return old_value, cohort_value
