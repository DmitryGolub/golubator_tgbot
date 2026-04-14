import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from src.celery_app import celery_app
from src.core.config import settings
from src.dao.meeting import MeetingDAO
from src.models.meeting import Meeting
from src.models.user import User
from src.tasks._db import celery_db, run_async
from src.utils.escape import e

logger = logging.getLogger(__name__)


def _format_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    from src.utils.tz import MSK

    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M MSK")


def _split_participants(
    meeting: Meeting,
) -> tuple[Optional[User], list[User]]:
    creator = next(
        (
            p
            for p in meeting.participants
            if p.telegram_id == meeting.mentor_telegram_id
        ),
        None,
    )
    others = [
        p
        for p in meeting.participants
        if not creator or p.telegram_id != creator.telegram_id
    ]
    return creator, others


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


async def _load_meeting(meeting_id: int) -> Optional[Meeting]:
    from src.core.database import async_session_maker

    async with async_session_maker() as session:
        query = (
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .options(
                joinedload(Meeting.participants),
            )
        )
        res = await session.execute(query)
        res = res.unique()
        return res.scalar_one_or_none()


async def _notify_created_async(meeting_id: int) -> None:
    async with celery_db():
        await _notify_created_inner(meeting_id)


async def _notify_created_inner(meeting_id: int) -> None:
    meeting = await _load_meeting(meeting_id)
    if not meeting:
        logger.warning("Meeting %s not found for notification", meeting_id)
        return

    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        creator, others = _split_participants(meeting)
        when = _format_dt(meeting.scheduled_at)
        creator_line = (
            f"Организатор: <b>{e(creator.name)}</b> @{e(creator.username)}"
            if creator
            else "Организатор не указан"
        )
        text = (
            "<b>Вам назначен созвон.</b>\n"
            f"{creator_line}\n"
            f"Когда: {when}\n"
            f"Описание: {e(meeting.description) or '—'}\n"
            f"Ссылка: {e(meeting.meeting_link) or '—'}"
        )
        for other in others:
            await _send_to_user(bot, other.telegram_id, text)
            logger.info(
                "Meeting %s: created notification sent to user %s",
                meeting_id,
                other.telegram_id,
            )
    finally:
        await bot.session.close()


async def _notify_reminder_async(meeting_id: int) -> None:
    async with celery_db():
        meeting = await _load_meeting(meeting_id)
        if not meeting:
            return

        bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        try:
            when = _format_dt(meeting.scheduled_at)
            link = e(meeting.meeting_link) or "—"
            for p in meeting.participants:
                partners = [
                    other
                    for other in meeting.participants
                    if other.telegram_id != p.telegram_id
                ]
                if partners:
                    partners_line = ", ".join(
                        f"<b>{e(other.name)}</b> @{e(other.username)}"
                        if other.username
                        else f"<b>{e(other.name)}</b>"
                        for other in partners
                    )
                else:
                    partners_line = "—"
                text = (
                    "<b>Напоминание о созвоне через ~5 минут.</b>\n"
                    f"С кем: {partners_line}\n"
                    f"Когда: {when}\n"
                    f"Ссылка: {link}"
                )
                await _send_to_user(bot, p.telegram_id, text)
        finally:
            await bot.session.close()


@celery_app.task(name="meeting.notify_created")
def notify_meeting_created(meeting_id: int) -> None:
    try:
        run_async(_notify_created_async(meeting_id))
    except Exception:
        logger.exception("notify_meeting_created failed for meeting %s", meeting_id)
        raise


@celery_app.task(name="meeting.notify_reminder")
def notify_meeting_reminder(meeting_id: int) -> None:
    try:
        run_async(_notify_reminder_async(meeting_id))
    except Exception:
        logger.exception("notify_meeting_reminder failed for meeting %s", meeting_id)
        raise


async def _archive_notion_page_async(notion_page_id: str) -> None:
    async with celery_db():
        from src.services.notion_sync_v2 import get_sync_service

        sync = get_sync_service()
        if sync and sync.event_repo:
            archived = await sync.event_repo._client.archive_page(notion_page_id)
            if archived:
                logger.info("Archived Notion page %s", notion_page_id)
            else:
                logger.warning("Failed to archive Notion page %s", notion_page_id)
        else:
            logger.warning(
                "No sync service available to archive page %s", notion_page_id
            )


@celery_app.task(name="meeting.archive_notion_page", ignore_result=True)
def archive_notion_page(notion_page_id: str) -> None:
    try:
        run_async(_archive_notion_page_async(notion_page_id))
    except Exception:
        logger.exception("archive_notion_page failed for %s", notion_page_id)
        raise


async def _auto_start_due_calls_async() -> None:
    async with celery_db():
        due = await MeetingDAO.find_due_unstarted_call_ids()
        if not due:
            return

        logger.info("auto_start_due_calls: found %d due meetings", len(due))
        for meeting_id, scheduled_at in due:
            try:
                started = await MeetingDAO.start_call(
                    meeting_id, started_at=scheduled_at
                )
            except IntegrityError:
                logger.warning(
                    "auto_start_due_calls: meeting %s skipped — "
                    "mentor already has an active call",
                    meeting_id,
                )
                continue

            if started is None:
                logger.info(
                    "auto_start_due_calls: meeting %s already started (race)",
                    meeting_id,
                )
                continue

            logger.info(
                "auto_start_due_calls: meeting %s auto-started at %s",
                meeting_id,
                scheduled_at,
            )


@celery_app.task(name="meeting.auto_start_due_calls", ignore_result=True)
def auto_start_due_calls() -> None:
    try:
        run_async(_auto_start_due_calls_async())
    except Exception:
        logger.exception("auto_start_due_calls failed")
        raise
