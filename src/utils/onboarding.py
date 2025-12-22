from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import aliased

from src.core.database import async_session_maker
from src.dao.meeting import MeetingDAO
from src.models.notification import Notification
from src.models.meeting import Meeting, MeetingUser
from src.models.user import User


FIRST_DELAY = timedelta(days=7)
SECOND_DELAY = timedelta(days=14)


def _reg_time(user: User) -> datetime:
    # fallback to now if registered_at is missing
    if user.registered_at:
        return user.registered_at if user.registered_at.tzinfo else user.registered_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _format_msk(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M MSK")


async def schedule_onboarding_notifications(user: User, *, base_time: datetime | None = None) -> None:
    """Schedule two onboarding notifications for the student."""
    reg_time = base_time or _reg_time(user)
    first_at = reg_time + FIRST_DELAY
    second_at = reg_time + SECOND_DELAY

    first_text = (
        "<b>Добро пожаловать!</b>\n"
        "Заполни, пожалуйста, форму и подготовь вопросы для созвона через неделю.\n"
        "Мы напомним ещё раз ближе к дате."
    )
    second_text = (
        "<b>Время созвониться с ментором.</b>\n"
        "Пора договориться о встрече и обсудить прогресс."
    )

    async with async_session_maker() as session:
        session.add(Notification(user_id=user.telegram_id, text=first_text, scheduled_at=first_at))
        session.add(Notification(user_id=user.telegram_id, text=second_text, scheduled_at=second_at))
        await session.commit()


async def schedule_onboarding_for_mentor(student: User, mentor_id: int) -> None:
    """Notify mentor about the upcoming onboarding call for a greeting student."""
    reg_time = _reg_time(student)
    meeting_time = reg_time + SECOND_DELAY
    when_text = _format_msk(meeting_time)

    now_text = (
        "<b>Новый ученик на онбординге.</b>\n"
        f"{student.name} @{student.username or ''}\n"
        f"Созвон запланирован на: {when_text}"
    )
    reminder_text = (
        "<b>Напоминание о созвоне с учеником.</b>\n"
        f"{student.name} @{student.username or ''}\n"
        f"Время: {when_text}"
    )

    async with async_session_maker() as session:
        session.add(Notification(user_id=mentor_id, text=now_text, scheduled_at=None))
        session.add(Notification(user_id=mentor_id, text=reminder_text, scheduled_at=meeting_time))
        await session.commit()

    # Create an onboarding meeting if it does not exist yet
    await _ensure_onboarding_meeting(student_id=student.telegram_id, mentor_id=mentor_id, scheduled_at=meeting_time)


async def _ensure_onboarding_meeting(student_id: int, mentor_id: int, scheduled_at: datetime) -> None:
    """Create an onboarding meeting for mentor+student if one does not already exist."""
    MU1 = aliased(MeetingUser)
    MU2 = aliased(MeetingUser)
    async with async_session_maker() as session:
        existing = await session.execute(
            select(Meeting)
            .join(MU1, MU1.meeting_id == Meeting.id)
            .join(MU2, MU2.meeting_id == Meeting.id)
            .where(MU1.user_id == student_id, MU2.user_id == mentor_id, Meeting.scheduled_at == scheduled_at)
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
    """Create immediate notification to student about mentor assignment."""
    mentor_username = f"@{mentor.username}" if mentor.username else ""
    text = (
        "<b>Вам назначен ментор.</b>\n"
        f"{mentor.name} {mentor_username}\n"
        "Напишите ему и договоритесь о созвоне."
    )
    async with async_session_maker() as session:
        session.add(
            Notification(
                user_id=student.telegram_id,
                text=text,
                scheduled_at=None,
            )
        )
        await session.commit()
