from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import String, case, func, select

from src.core.database import async_session_maker
from src.models.cohort import Cohort, UserCohort
from src.models.meeting import Meeting
from src.models.survey_session import SurveyAnswer, SurveySession
from src.models.user import User


@dataclass(slots=True)
class EducationFeedbackRow:
    direction: str | None
    mentor_name: str | None
    total_meetings: int
    surveys_completed: int
    avg_rating: float | None


class EducationFeedbackDAO:
    @staticmethod
    async def get_summary(
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[EducationFeedbackRow]:
        async with async_session_maker() as session:
            mentor_name = func.coalesce(User.name, "—").label("mentor_name")
            direction = func.coalesce(Cohort.value, "—").label("direction")
            total = func.count(Meeting.id.distinct()).label("total_meetings")

            survey_completed = func.count(
                case(
                    (SurveySession.status == "completed", SurveySession.id),
                )
            ).label("surveys_completed")

            avg_rating = func.avg(SurveyAnswer.value_int).label("avg_rating")

            query = (
                select(direction, mentor_name, total, survey_completed, avg_rating)
                .select_from(Meeting)
                .outerjoin(User, User.telegram_id == Meeting.mentor_telegram_id)
                .outerjoin(
                    UserCohort,
                    UserCohort.user_telegram_id == Meeting.student_telegram_id,
                )
                .outerjoin(
                    Cohort,
                    (Cohort.id == UserCohort.cohort_id) & (Cohort.type == "Category"),
                )
                .outerjoin(
                    SurveySession,
                    (SurveySession.context_id == func.cast(Meeting.id, String))
                    & (
                        SurveySession.context_type.in_(
                            ["post_call_student", "mentor_feedback"]
                        )
                    ),
                )
                .outerjoin(
                    SurveyAnswer,
                    (SurveyAnswer.session_id == SurveySession.id)
                    & (SurveyAnswer.value_int.isnot(None)),
                )
                .where(Meeting.event_type == "Обучение")
            )

            if date_from is not None:
                query = query.where(Meeting.scheduled_at >= date_from)
            if date_to is not None:
                query = query.where(Meeting.scheduled_at <= date_to)

            query = query.group_by(direction, mentor_name).order_by(
                direction, mentor_name
            )

            result = await session.execute(query)
            return [
                EducationFeedbackRow(
                    direction=row.direction,
                    mentor_name=row.mentor_name,
                    total_meetings=row.total_meetings,
                    surveys_completed=row.surveys_completed,
                    avg_rating=float(row.avg_rating) if row.avg_rating else None,
                )
                for row in result.all()
            ]
