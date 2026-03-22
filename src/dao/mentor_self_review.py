from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError

from src.core.database import async_session_maker
from src.models.mentor_self_review import MentorSelfReview
from src.models.role import RoleModel
from src.models.user import User


class MentorSelfReviewDAO:
    @classmethod
    async def exists_for_period(cls, mentor_id: int, period: str) -> bool:
        async with async_session_maker() as session:
            query = select(
                exists().where(
                    MentorSelfReview.mentor_id == mentor_id,
                    MentorSelfReview.period == period,
                )
            )
            result = await session.execute(query)
            return bool(result.scalar())

    @classmethod
    async def submit_review(
        cls,
        *,
        mentor_id: int,
        workload: int,
        pigeon_stupidity: int,
        avg_neuromutation: int,
        comment: str | None,
        period: str,
    ) -> tuple[MentorSelfReview, bool]:
        async with async_session_maker() as session:
            try:
                async with session.begin():
                    existing = await session.execute(
                        select(MentorSelfReview).where(
                            MentorSelfReview.mentor_id == mentor_id,
                            MentorSelfReview.period == period,
                        )
                    )
                    existing_review = existing.scalar_one_or_none()
                    if existing_review:
                        return existing_review, True

                    review = MentorSelfReview(
                        mentor_id=mentor_id,
                        workload=workload,
                        pigeon_stupidity=pigeon_stupidity,
                        avg_neuromutation=avg_neuromutation,
                        comment=comment,
                        period=period,
                    )
                    session.add(review)
            except IntegrityError:
                await session.rollback()
                existing = await session.execute(
                    select(MentorSelfReview).where(
                        MentorSelfReview.mentor_id == mentor_id,
                        MentorSelfReview.period == period,
                    )
                )
                existing_review = existing.scalar_one_or_none()
                if existing_review:
                    return existing_review, True
                raise

            await session.refresh(review)
            return review, False

    @classmethod
    async def get_mentors_without_review_for_period(cls, period: str) -> list[User]:
        async with async_session_maker() as session:
            query = (
                select(User)
                .join(RoleModel, User.role_id == RoleModel.id)
                .where(
                    RoleModel.is_mentor.is_(True),
                    ~exists().where(
                        MentorSelfReview.mentor_id == User.telegram_id,
                        MentorSelfReview.period == period,
                    ),
                )
            )
            result = await session.execute(query)
            return list(result.scalars().all())
