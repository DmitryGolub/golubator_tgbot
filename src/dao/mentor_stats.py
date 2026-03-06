from datetime import datetime
from typing import Optional

from sqlalchemy import func, select

from src.core.database import async_session_maker
from src.models.meeting import Meeting, MeetingUser
from src.models.survey import SurveyResponse


class MentorStatsDAO:
    @classmethod
    async def get_stats(
        cls,
        mentor_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict:
        """
        Return aggregated survey statistics for a mentor.

        Counts completed meetings where the mentor was a participant.
        Calculates averages only from meetings that have survey responses.
        """
        async with async_session_maker() as session:
            # Base filter: meetings where this mentor participated and completed
            base_filter = [
                MeetingUser.user_id == mentor_id,
                Meeting.completed_at.isnot(None),
            ]
            if date_from is not None:
                base_filter.append(Meeting.completed_at >= date_from)
            if date_to is not None:
                base_filter.append(Meeting.completed_at <= date_to)

            # Count total completed calls
            calls_query = (
                select(func.count(Meeting.id))
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(*base_filter)
            )
            total_calls = (await session.execute(calls_query)).scalar() or 0

            # Aggregate survey metrics
            stats_query = (
                select(
                    func.count(SurveyResponse.id).label("total_surveys"),
                    func.avg(SurveyResponse.mentor_style).label("avg_mentor_style"),
                    func.avg(SurveyResponse.knowledge_depth).label("avg_knowledge_depth"),
                    func.avg(SurveyResponse.understanding).label("avg_understanding"),
                    func.avg(
                        (
                            SurveyResponse.mentor_style
                            + SurveyResponse.knowledge_depth
                            + SurveyResponse.understanding
                        )
                        / 3.0
                    ).label("avg_satisfaction"),
                )
                .select_from(Meeting)
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .join(SurveyResponse, SurveyResponse.call_id == Meeting.id)
                .where(*base_filter)
            )
            row = (await session.execute(stats_query)).one()

            return {
                "mentor_id": mentor_id,
                "total_calls": total_calls,
                "total_surveys": row.total_surveys or 0,
                "avg_mentor_style": (
                    round(float(row.avg_mentor_style), 2)
                    if row.avg_mentor_style is not None
                    else None
                ),
                "avg_knowledge_depth": (
                    round(float(row.avg_knowledge_depth), 2)
                    if row.avg_knowledge_depth is not None
                    else None
                ),
                "avg_understanding": (
                    round(float(row.avg_understanding), 2)
                    if row.avg_understanding is not None
                    else None
                ),
                "avg_satisfaction": (
                    round(float(row.avg_satisfaction), 2)
                    if row.avg_satisfaction is not None
                    else None
                ),
            }
