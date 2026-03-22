import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload

from src.bot.keyboards.survey import survey_start_keyboard
from src.celery_app import celery_app
from src.core.config import settings
from src.models.meeting import Meeting
from src.models.user import User
from src.utils.roles import is_mentor, is_student
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)


def _format_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    if dt.tzinfo:
        return dt.astimezone(dt.tzinfo).strftime("%d.%m.%Y %H:%M MSK")
    return dt.strftime("%d.%m.%Y %H:%M MSK")


def _split_participants(meeting: Meeting) -> tuple[Optional[User], Optional[User]]:
    mentor = next((p for p in meeting.participants if is_mentor(p)), None)
    student = next((p for p in meeting.participants if is_student(p)), None)
    if not student and mentor:
        student = next(
            (p for p in meeting.participants if p.telegram_id != mentor.telegram_id),
            None,
        )
    return mentor, student


def _survey_notification_text(call_id: int) -> str:
    return (
        "<b>Созвон завершён.</b>\n"
        "Пожалуйста, оставьте обратную связь по встрече.\n"
        f"ID созвона: <b>#{call_id}</b>\n"
        f"Или отправьте команду: <code>/survey {call_id}</code>"
    )


async def _send_to_user(
    user_id: int,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup)
    finally:
        await bot.session.close()


async def _send_to_student(
    student: Optional[User],
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if not student:
        return
    await _send_to_user(student.telegram_id, text, reply_markup=reply_markup)


async def _load_meeting(meeting_id: int) -> Optional[Meeting]:
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            query = (
                select(Meeting)
                .where(Meeting.id == meeting_id)
                .options(
                    joinedload(Meeting.participants).joinedload(User.role_rel),
                )
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
            query = select(Meeting).where(Meeting.id == meeting_id)
            result = await session.execute(query)
            meeting = result.scalar_one_or_none()
            if not meeting or meeting.completed_at is not None:
                return

            meeting.completed_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("Completed meeting %s via scheduled task", meeting_id)
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
            )
            result = await session.execute(query)
            meetings = result.scalars().all()

            for meeting in meetings:
                meeting.completed_at = cutoff

            if meetings:
                await session.commit()
            logger.info("Cleanup stale meetings: cutoff=%s, completed=%s", cutoff, len(meetings))
    finally:
        await engine.dispose()

    for student_id, call_id in survey_notifications:
        await _send_to_user(
            student_id,
            _survey_notification_text(call_id),
            reply_markup=survey_start_keyboard(call_id),
        )


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
