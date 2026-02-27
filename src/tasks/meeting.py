import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload

from src.celery_app import celery_app
from src.core.config import settings
from src.models.meeting import Meeting
from src.models.notification import Notification
from src.models.user import Role, User

logger = logging.getLogger(__name__)


def _format_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    if dt.tzinfo:
        return dt.astimezone(dt.tzinfo).strftime("%d.%m.%Y %H:%M MSK")
    return dt.strftime("%d.%m.%Y %H:%M MSK")


def _split_participants(meeting: Meeting) -> tuple[Optional[User], Optional[User]]:
    mentor = next((p for p in meeting.participants if p.role == Role.mentor), None)
    student = next((p for p in meeting.participants if p.role == Role.student), None)
    if not student and mentor:
        student = next(
            (p for p in meeting.participants if p.telegram_id != mentor.telegram_id),
            None,
        )
    return mentor, student


def _survey_notification_text(meeting: Meeting) -> str:
    return (
        "<b>Созвон завершён.</b>\n"
        "Пожалуйста, оставьте обратную связь по встрече.\n"
        f"ID созвона: <b>#{meeting.id}</b>"
    )


async def _send_to_student(student: Optional[User], text: str) -> None:
    if not student:
        return
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        await bot.send_message(student.telegram_id, text)
    finally:
        await bot.session.close()


async def _load_meeting(meeting_id: int) -> Optional[Meeting]:
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            query = (
                select(Meeting)
                .where(Meeting.id == meeting_id)
                .options(joinedload(Meeting.participants))
            )
            res = await session.execute(query)
            res = res.unique()
            return res.scalar_one_or_none()
    finally:
        await engine.dispose()


async def _notify_created_async(meeting_id: int) -> None:
    meeting = await _load_meeting(meeting_id)
    if not meeting:
        return

    mentor, student = _split_participants(meeting)
    when = _format_dt(meeting.scheduled_at)
    mentor_line = (
        f"Ментор: <b>{mentor.name}</b> @{mentor.username}"
        if mentor
        else "Ментор не указан"
    )
    text = (
        "<b>Вам назначен созвон.</b>\n"
        f"{mentor_line}\n"
        f"Когда: {when}\n"
        f"Описание: {meeting.description or '—'}\n"
        f"Ссылка: {meeting.meeting_link or '—'}"
    )
    await _send_to_student(student, text)


async def _notify_reminder_async(meeting_id: int) -> None:
    meeting = await _load_meeting(meeting_id)
    if not meeting:
        return

    _, student = _split_participants(meeting)
    when = _format_dt(meeting.scheduled_at)
    text = (
        "<b>Напоминание о созвоне через ~5 минут.</b>\n"
        f"Когда: {when}\n"
        f"Ссылка: {meeting.meeting_link or '—'}"
    )
    await _send_to_student(student, text)


async def _complete_meeting_async(meeting_id: int) -> bool:
    now = datetime.now(timezone.utc)
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with Session() as session:
            query = (
                select(Meeting)
                .where(Meeting.id == meeting_id)
                .options(joinedload(Meeting.participants))
            )
            result = await session.execute(query)
            meeting = result.unique().scalar_one_or_none()

            if not meeting:
                logger.info("Meeting %s not found for completion", meeting_id)
                return False

            if meeting.completed_at is not None:
                logger.info("Meeting %s already completed at %s", meeting_id, meeting.completed_at)
                return False

            meeting.completed_at = now
            if meeting.survey_available_at is None:
                meeting.survey_available_at = now

            _, student = _split_participants(meeting)
            if student:
                session.add(
                    Notification(
                        user_id=student.telegram_id,
                        text=_survey_notification_text(meeting),
                        scheduled_at=now,
                    )
                )

            await session.commit()
            logger.info("Meeting %s completed at %s", meeting_id, now)
            return True
    finally:
        await engine.dispose()


async def _cleanup_stale_async() -> None:
    cutoff = datetime.now(timezone.utc)
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with Session() as session:
            query = (
                select(Meeting)
                .where(
                    Meeting.scheduled_at <= cutoff,
                    Meeting.completed_at.is_(None),
                )
                .options(joinedload(Meeting.participants))
            )
            result = await session.execute(query)
            meetings = result.unique().scalars().all()

            completed = 0
            for meeting in meetings:
                meeting.completed_at = cutoff
                if meeting.survey_available_at is None:
                    meeting.survey_available_at = cutoff

                _, student = _split_participants(meeting)
                if student:
                    session.add(
                        Notification(
                            user_id=student.telegram_id,
                            text=_survey_notification_text(meeting),
                            scheduled_at=cutoff,
                        )
                    )
                completed += 1

            if completed:
                await session.commit()
            logger.info("Cleanup stale meetings: cutoff=%s, completed=%s", cutoff, completed)
    finally:
        await engine.dispose()


@celery_app.task(name="meeting.notify_created")
def notify_meeting_created(meeting_id: int) -> None:
    asyncio.run(_notify_created_async(meeting_id))


@celery_app.task(name="meeting.notify_reminder")
def notify_meeting_reminder(meeting_id: int) -> None:
    asyncio.run(_notify_reminder_async(meeting_id))


@celery_app.task(name="meeting.complete")
def complete_meeting(meeting_id: int) -> None:
    asyncio.run(_complete_meeting_async(meeting_id))


@celery_app.task(name="meeting.delete")
def delete_meeting(meeting_id: int) -> None:
    # Backward-compatibility alias for already planned tasks.
    asyncio.run(_complete_meeting_async(meeting_id))


@celery_app.task(name="meeting.cleanup_stale")
def cleanup_stale_meetings() -> None:
    asyncio.run(_cleanup_stale_async())
