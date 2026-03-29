from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import String, case, func, select

from src.core.database import async_session_maker
from src.models.cohort import Cohort, UserCohort
from src.models.meeting import Meeting
from src.models.survey_session import SurveySession
from src.models.user import User


@dataclass(slots=True)
class JobSearchRow:
    direction: str | None
    mentor_name: str | None
    total_meetings: int
    surveys_completed: int


class JobSearchReportDAO:
    @staticmethod
    async def get_summary(
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[JobSearchRow]:
        async with async_session_maker() as session:
            mentor_name = func.coalesce(User.name, "—").label("mentor_name")
            direction = func.coalesce(Cohort.value, "—").label("direction")
            total = func.count(Meeting.id.distinct()).label("total_meetings")

            survey_completed = func.count(
                case(
                    (SurveySession.status == "completed", SurveySession.id),
                )
            ).label("surveys_completed")

            query = (
                select(direction, mentor_name, total, survey_completed)
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
                .where(Meeting.event_type == "Поиск работы")
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
                JobSearchRow(
                    direction=row.direction,
                    mentor_name=row.mentor_name,
                    total_meetings=row.total_meetings,
                    surveys_completed=row.surveys_completed,
                )
                for row in result.all()
            ]
