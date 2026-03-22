import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload

from src.celery_app import celery_app
from src.core.config import settings
from src.models.meeting import Meeting
from src.models.user import User
from src.utils.roles import is_mentor, is_student

logger = logging.getLogger(__name__)


def _format_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    from src.utils.tz import MSK

    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M MSK")


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
    bot: Bot,
    user_id: int,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    await bot.send_message(user_id, text, reply_markup=reply_markup)


async def _send_to_student(
    bot: Bot,
    student: Optional[User],
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if not student:
        return
    await _send_to_user(bot, student.telegram_id, text, reply_markup=reply_markup)


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
        logger.warning("Meeting %s not found for notification", meeting_id)
        return

    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
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
        await _send_to_student(bot, student, text)
        if student:
            logger.info(
                "Meeting %s: created notification sent to user %s",
                meeting_id,
                student.telegram_id,
            )
    finally:
        await bot.session.close()


async def _notify_reminder_async(meeting_id: int) -> None:
    meeting = await _load_meeting(meeting_id)
    if not meeting:
        return

    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        _, student = _split_participants(meeting)
        when = _format_dt(meeting.scheduled_at)
        text = (
            "<b>Напоминание о созвоне через ~5 минут.</b>\n"
            f"Когда: {when}\n"
            f"Ссылка: {meeting.meeting_link or '—'}"
        )
        await _send_to_student(bot, student, text)
    finally:
        await bot.session.close()


async def _complete_meeting_async(meeting_id: int) -> bool:
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            query = select(Meeting).where(Meeting.id == meeting_id)
            result = await session.execute(query)
            meeting = result.scalar_one_or_none()
            if not meeting or meeting.completed_at is not None:
                return False

            meeting.completed_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("Completed meeting %s via scheduled task", meeting_id)
            return True
    finally:
        await engine.dispose()


async def _cleanup_stale_async() -> None:
    cutoff = datetime.now(timezone.utc)
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            query = select(Meeting).where(
                Meeting.scheduled_at <= cutoff,
                Meeting.completed_at.is_(None),
            )
            result = await session.execute(query)
            meetings = result.scalars().all()

            for meeting in meetings:
                meeting.completed_at = cutoff

            if meetings:
                await session.commit()
            logger.info(
                "Cleanup stale meetings: cutoff=%s, completed=%s", cutoff, len(meetings)
            )
    finally:
        await engine.dispose()


@celery_app.task(name="meeting.notify_created")
def notify_meeting_created(meeting_id: int) -> None:
    try:
        asyncio.run(_notify_created_async(meeting_id))
    except Exception as exc:
        logger.error(
            "notify_meeting_created failed for meeting %s: %s", meeting_id, exc
        )


@celery_app.task(name="meeting.notify_reminder")
def notify_meeting_reminder(meeting_id: int) -> None:
    try:
        asyncio.run(_notify_reminder_async(meeting_id))
    except Exception as exc:
        logger.error(
            "notify_meeting_reminder failed for meeting %s: %s", meeting_id, exc
        )


@celery_app.task(name="meeting.complete")
def complete_meeting(meeting_id: int) -> None:
    try:
        asyncio.run(_complete_meeting_async(meeting_id))
    except Exception as exc:
        logger.error("complete_meeting failed for meeting %s: %s", meeting_id, exc)


async def _delete_meeting_async(meeting_id: int) -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            stmt = delete(Meeting).where(Meeting.id == meeting_id)
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount:
                logger.info("Deleted meeting %s via scheduled task", meeting_id)
            else:
                logger.warning("Meeting %s not found for deletion", meeting_id)
    finally:
        await engine.dispose()


@celery_app.task(name="meeting.delete")
def delete_meeting(meeting_id: int) -> None:
    try:
        asyncio.run(_delete_meeting_async(meeting_id))
    except Exception as exc:
        logger.error("delete_meeting failed for meeting %s: %s", meeting_id, exc)


@celery_app.task(name="meeting.cleanup_stale")
def cleanup_stale_meetings() -> None:
    try:
        asyncio.run(_cleanup_stale_async())
    except Exception as exc:
        logger.error("cleanup_stale_meetings failed: %s", exc)
