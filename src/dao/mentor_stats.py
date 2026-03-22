from datetime import datetime
from typing import Optional

from sqlalchemy import String, func, select
from sqlalchemy.sql.expression import cast

from src.core.database import async_session_maker
from src.models.meeting import Meeting, MeetingUser
from src.models.survey_session import SurveyAnswer, SurveySession
from src.models.survey_template import SurveyQuestion, SurveyTemplate


class MentorStatsDAO:
    @classmethod
    async def get_stats(
        cls,
        mentor_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict:
        """Return aggregated survey statistics for a mentor.

        Counts completed meetings where the mentor was a participant.
        Calculates averages from completed survey sessions (post_call_student template).
        """
        async with async_session_maker() as session:
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

            # Survey filter: join through Meeting to filter by mentor
            survey_meeting_filter = [
                SurveyTemplate.slug == "post_call_student",
                SurveySession.context_type == "meeting",
                SurveySession.status == "completed",
                MeetingUser.user_id == mentor_id,
            ]
            if date_from is not None:
                survey_meeting_filter.append(Meeting.completed_at >= date_from)
            if date_to is not None:
                survey_meeting_filter.append(Meeting.completed_at <= date_to)

            # Count completed survey sessions for this mentor's meetings
            survey_count_query = (
                select(func.count(SurveySession.id))
                .join(SurveyTemplate, SurveySession.template_id == SurveyTemplate.id)
                .join(Meeting, cast(Meeting.id, String) == SurveySession.context_id)
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(*survey_meeting_filter)
            )
            total_surveys = (await session.execute(survey_count_query)).scalar() or 0

            # Calculate averages from rating answers
            # Rating questions in post_call_student: sort_order 2,3,4
            avg_query = (
                select(
                    SurveyQuestion.sort_order,
                    func.avg(SurveyAnswer.value_int).label("avg_value"),
                )
                .select_from(SurveyAnswer)
                .join(SurveySession, SurveyAnswer.session_id == SurveySession.id)
                .join(SurveyQuestion, SurveyAnswer.question_id == SurveyQuestion.id)
                .join(SurveyTemplate, SurveySession.template_id == SurveyTemplate.id)
                .join(Meeting, cast(Meeting.id, String) == SurveySession.context_id)
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(
                    SurveyTemplate.slug == "post_call_student",
                    SurveySession.context_type == "meeting",
                    SurveySession.status == "completed",
                    SurveyQuestion.question_type == "rating",
                    SurveyAnswer.value_int.isnot(None),
                    MeetingUser.user_id == mentor_id,
                )
                .group_by(SurveyQuestion.sort_order)
            )
            avg_rows = (await session.execute(avg_query)).fetchall()
            avgs = {row.sort_order: round(float(row.avg_value), 2) for row in avg_rows}

            return {
                "mentor_id": mentor_id,
                "total_calls": total_calls,
                "total_surveys": total_surveys,
                "avg_mentor_style": avgs.get(2),
                "avg_knowledge_depth": avgs.get(3),
                "avg_understanding": avgs.get(4),
                "avg_satisfaction": (
                    round(
                        sum(v for v in [avgs.get(2), avgs.get(3), avgs.get(4)] if v)
                        / max(
                            sum(
                                1 for v in [avgs.get(2), avgs.get(3), avgs.get(4)] if v
                            ),
                            1,
                        ),
                        2,
                    )
                    if any(avgs.get(i) for i in (2, 3, 4))
                    else None
                ),
            }
