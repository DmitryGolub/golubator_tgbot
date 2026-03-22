from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.database import async_session_maker
from src.models.meeting import Meeting
from src.models.survey_session import SurveySession
from src.models.user import User


class FeedbackExportDAO:
    @classmethod
    async def get_completed_meetings(
        cls,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[Meeting]:
        async with async_session_maker() as session:
            call_started_at = func.coalesce(Meeting.scheduled_at, Meeting.created_at)

            query = (
                select(Meeting)
                .where(Meeting.completed_at.isnot(None))
                .options(selectinload(Meeting.participants))
                .order_by(call_started_at.asc(), Meeting.id.asc())
            )
            if date_from is not None:
                query = query.where(call_started_at >= date_from)
            if date_to is not None:
                query = query.where(call_started_at <= date_to)

            result = await session.execute(query)
            return list(result.unique().scalars().all())

    @classmethod
    async def get_sessions_for_meetings(
        cls,
        meeting_ids: list[int],
    ) -> dict[str, list[SurveySession]]:
        """Returns {f"{template_slug}:{meeting_id}": session} mapping."""
        if not meeting_ids:
            return {}

        async with async_session_maker() as session:
            str_ids = [str(mid) for mid in meeting_ids]
            query = (
                select(SurveySession)
                .where(
                    SurveySession.context_type == "meeting",
                    SurveySession.context_id.in_(str_ids),
                    SurveySession.status == "completed",
                )
                .options(
                    selectinload(SurveySession.answers),
                    selectinload(SurveySession.template),
                )
            )
            result = await session.execute(query)
            sessions = result.unique().scalars().all()

            mapping: dict[str, SurveySession] = {}
            for s in sessions:
                key = f"{s.template.slug}:{s.context_id}"
                mapping[key] = s
            return mapping

    @classmethod
    async def get_users_by_ids(cls, user_ids: set[int]) -> dict[int, User]:
        if not user_ids:
            return {}

        async with async_session_maker() as session:
            query = select(User).where(User.telegram_id.in_(user_ids))
            result = await session.execute(query)
            users = result.scalars().all()
            return {user.telegram_id: user for user in users}
