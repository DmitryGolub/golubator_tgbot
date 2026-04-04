from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, func, select
from sqlalchemy.sql.expression import cast

from src.core.database import async_session_maker
from src.models.meeting import Meeting, MeetingUser
from src.models.survey_session import SessionStatus, SurveyAnswer, SurveySession
from src.models.survey_template import SurveyQuestion, SurveyTemplate

_POST_CALL_STUDENT_SLUG = "post_call_student"
# sort_order values in SurveyQuestion for the post_call_student template:
#   2 = mentor_style, 3 = knowledge_depth, 4 = understanding
_MENTOR_STYLE_SORT_ORDER = 2
_KNOWLEDGE_DEPTH_SORT_ORDER = 3
_UNDERSTANDING_SORT_ORDER = 4


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
            # Count all calls (regardless of completed_at)
            calls_filter = [MeetingUser.user_id == mentor_id]
            if date_from is not None:
                calls_filter.append(Meeting.scheduled_at >= date_from)
            if date_to is not None:
                calls_filter.append(Meeting.scheduled_at <= date_to)

            calls_query = (
                select(func.count(Meeting.id))
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(*calls_filter)
            )
            total_calls = (await session.execute(calls_query)).scalar() or 0

            # Survey filter: join through Meeting to filter by mentor
            survey_meeting_filter = [
                SurveyTemplate.slug == _POST_CALL_STUDENT_SLUG,
                SurveySession.context_type == "meeting",
                SurveySession.context_id.op("~")(r"^\d+$"),
                SurveySession.status == SessionStatus.completed,
                MeetingUser.user_id == mentor_id,
            ]
            if date_from is not None:
                survey_meeting_filter.append(Meeting.completed_at >= date_from)
            if date_to is not None:
                survey_meeting_filter.append(Meeting.completed_at <= date_to)

            # CTE: only sessions with numeric context_id (safe for CAST)
            numeric_sessions = (
                select(SurveySession.id.label("session_id"))
                .where(
                    SurveySession.context_type == "meeting",
                    SurveySession.context_id.op("~")(r"^\d+$"),
                )
                .cte("numeric_sessions")
            )

            # Count completed survey sessions for this mentor's meetings
            survey_count_query = (
                select(func.count(SurveySession.id))
                .join(
                    numeric_sessions,
                    numeric_sessions.c.session_id == SurveySession.id,
                )
                .join(SurveyTemplate, SurveySession.template_id == SurveyTemplate.id)
                .join(Meeting, Meeting.id == cast(SurveySession.context_id, Integer))
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
                .join(
                    numeric_sessions,
                    numeric_sessions.c.session_id == SurveySession.id,
                )
                .join(SurveyQuestion, SurveyAnswer.question_id == SurveyQuestion.id)
                .join(SurveyTemplate, SurveySession.template_id == SurveyTemplate.id)
                .join(Meeting, Meeting.id == cast(SurveySession.context_id, Integer))
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(
                    SurveyTemplate.slug == _POST_CALL_STUDENT_SLUG,
                    SurveySession.context_type == "meeting",
                    SurveySession.context_id.op("~")(r"^\d+$"),
                    SurveySession.status == SessionStatus.completed,
                    SurveyQuestion.question_type == "rating",
                    SurveyAnswer.value_int.isnot(None),
                    MeetingUser.user_id == mentor_id,
                )
                .group_by(SurveyQuestion.sort_order)
            )
            avg_rows = (await session.execute(avg_query)).fetchall()
            avgs = {row.sort_order: round(float(row.avg_value), 2) for row in avg_rows}

            rating_orders = (
                _MENTOR_STYLE_SORT_ORDER,
                _KNOWLEDGE_DEPTH_SORT_ORDER,
                _UNDERSTANDING_SORT_ORDER,
            )
            return {
                "mentor_id": mentor_id,
                "total_calls": total_calls,
                "total_surveys": total_surveys,
                "avg_mentor_style": avgs.get(_MENTOR_STYLE_SORT_ORDER),
                "avg_knowledge_depth": avgs.get(_KNOWLEDGE_DEPTH_SORT_ORDER),
                "avg_understanding": avgs.get(_UNDERSTANDING_SORT_ORDER),
                "avg_satisfaction": (
                    round(
                        sum(
                            v
                            for v in [avgs.get(o) for o in rating_orders]
                            if v is not None
                        )
                        / max(
                            sum(1 for o in rating_orders if avgs.get(o) is not None),
                            1,
                        ),
                        2,
                    )
                    if any(avgs.get(o) is not None for o in rating_orders)
                    else None
                ),
            }
