import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import aliased

from src.core.database import async_session_maker
from src.dao.meeting import MeetingDAO
from src.models.meeting import Meeting, MeetingUser
from src.models.user import User

logger = logging.getLogger(__name__)

FIRST_DELAY = timedelta(days=7)
SECOND_DELAY = timedelta(days=14)


def _reg_time(user: User) -> datetime:
    if user.registered_at:
        return (
            user.registered_at
            if user.registered_at.tzinfo
            else user.registered_at.replace(tzinfo=timezone.utc)
        )
    return datetime.now(timezone.utc)


async def schedule_onboarding_notifications(
    user: User, *, base_time: datetime | None = None
) -> None:
    """Schedule onboarding via trigger system (legacy Notification table removed)."""
    logger.info(
        "Onboarding scheduled for user %s (use trigger rules for notifications)",
        user.telegram_id,
    )


async def schedule_onboarding_for_mentor(student: User, mentor_id: int) -> None:
    """Create onboarding meeting for mentor+student."""
    reg_time = _reg_time(student)
    meeting_time = reg_time + SECOND_DELAY

    await _ensure_onboarding_meeting(
        student_id=student.telegram_id, mentor_id=mentor_id, scheduled_at=meeting_time
    )


async def _ensure_onboarding_meeting(
    student_id: int, mentor_id: int, scheduled_at: datetime
) -> None:
    MU1 = aliased(MeetingUser)
    MU2 = aliased(MeetingUser)
    async with async_session_maker() as session:
        existing = await session.execute(
            select(Meeting)
            .join(MU1, MU1.meeting_id == Meeting.id)
            .join(MU2, MU2.meeting_id == Meeting.id)
            .where(
                MU1.user_id == student_id,
                MU2.user_id == mentor_id,
                Meeting.scheduled_at == scheduled_at,
            )
        )
        meeting = existing.scalar_one_or_none()
    if meeting:
        return

    await MeetingDAO.create_with_participants(
        description="Первый созвон с ментором (онбординг)",
        meeting_link=None,
        scheduled_at=scheduled_at,
        mentor_id=mentor_id,
        student_id=student_id,
    )


async def notify_student_new_mentor(student: User, mentor: User) -> None:
    """Log mentor assignment (actual notification via trigger rules)."""
    logger.info(
        "Mentor %s assigned to student %s (use trigger rules for notification)",
        mentor.telegram_id,
        student.telegram_id,
    )
