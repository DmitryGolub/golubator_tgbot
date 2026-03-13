from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from src.core.database import async_session_maker
from src.models.meeting import Meeting
from src.models.mentor_feedback import MentorFeedback
from src.models.survey import SurveyResponse
from src.models.user import User


class FeedbackExportDAO:
    @classmethod
    async def get_feedback_meetings(
        cls,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[Meeting]:
        async with async_session_maker() as session:
            call_started_at = func.coalesce(Meeting.scheduled_at, Meeting.created_at)
            survey_exists = select(SurveyResponse.id).where(
                SurveyResponse.call_id == Meeting.id
            ).exists()
            mentor_feedback_exists = select(MentorFeedback.id).where(
                MentorFeedback.call_id == Meeting.id
            ).exists()

            query = (
                select(Meeting)
                .where(or_(survey_exists, mentor_feedback_exists))
                .options(
                    selectinload(Meeting.participants),
                    selectinload(Meeting.survey_response),
                )
                .order_by(call_started_at.asc(), Meeting.id.asc())
            )
            if date_from is not None:
                query = query.where(call_started_at >= date_from)
            if date_to is not None:
                query = query.where(call_started_at <= date_to)

            result = await session.execute(query)
            return result.scalars().all()

    @classmethod
    async def get_mentor_feedback_map(
        cls,
        call_ids: list[int],
    ) -> dict[int, MentorFeedback]:
        if not call_ids:
            return {}

        async with async_session_maker() as session:
            query = select(MentorFeedback).where(MentorFeedback.call_id.in_(call_ids))
            result = await session.execute(query)
            feedbacks = result.scalars().all()
            return {feedback.call_id: feedback for feedback in feedbacks}

    @classmethod
    async def get_users_by_ids(cls, user_ids: set[int]) -> dict[int, User]:
        if not user_ids:
            return {}

        async with async_session_maker() as session:
            query = select(User).where(User.telegram_id.in_(user_ids))
            result = await session.execute(query)
            users = result.scalars().all()
            return {user.telegram_id: user for user in users}
