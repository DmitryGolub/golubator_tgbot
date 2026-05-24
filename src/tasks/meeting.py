import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from src.celery_app import celery_app
from src.dao.meeting import MeetingDAO
from src.dao.meeting_notification import MeetingNotificationDAO
from src.dao.user import UserDAO
from src.models.meeting import (
    Meeting,
    MeetingNotificationType,
    MeetingUser,
    ProposalStatus,
)
from src.models.user import User
from src.tasks._db import celery_db, get_worker_bot, run_async
from src.utils.bot_send import safe_send_message
from src.utils.escape import e

logger = logging.getLogger(__name__)

CALL_DURATION_TEMPLATE_SLUG = "call_duration_actual"
CALL_DURATION_CONTEXT_TYPE = "call_duration"


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


async def _send_meeting_notification(
    meeting_id: int,
    user_id: int,
    notification_type: MeetingNotificationType,
    text: str,
    *,
    scheduled_window: datetime | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    bot: Bot | None = None,
) -> bool:
    """Send idempotent meeting notification. Returns True if sent or already sent."""
    if bot is None:
        bot = get_worker_bot()

    user = await UserDAO.find_one_or_none(telegram_id=user_id)
    if user is None or user.registered_at is None or user.telegram_id < 0:
        logger.info(
            "Skipping %s for user %s (unregistered or placeholder)",
            notification_type.value,
            user_id,
        )
        return False

    notification, created = await MeetingNotificationDAO.try_create(
        meeting_id=meeting_id,
        user_id=user_id,
        notification_type=notification_type.value,
        scheduled_window=scheduled_window,
    )
    if not created:
        logger.debug(
            "Notification %s already sent for meeting %s user %s window %s",
            notification_type.value,
            meeting_id,
            user_id,
            scheduled_window,
        )
        return False

    try:
        sent = await safe_send_message(bot, user, text, reply_markup=reply_markup)
        if sent:
            await MeetingNotificationDAO.mark_sent(notification.id)
            logger.info(
                "Sent %s for meeting %s user %s",
                notification_type.value,
                meeting_id,
                user_id,
            )
            return True
        else:
            await MeetingNotificationDAO.mark_failed(
                notification.id, "safe_send_message returned False"
            )
            return False
    except Exception as exc:
        await MeetingNotificationDAO.mark_failed(notification.id, str(exc))
        logger.warning(
            "Failed to send %s for meeting %s user %s: %s",
            notification_type.value,
            meeting_id,
            user_id,
            exc,
        )
        return False


async def _send_confirmation_request(
    meeting_id: int,
    user_id: int,
    *,
    bot: Bot | None = None,
    scheduled_window: datetime | None = None,
    notification_type: MeetingNotificationType = MeetingNotificationType.confirmation_request,
) -> bool:
    """Send a confirmation request to a single participant if still pending."""
    meeting = await _load_meeting(meeting_id)
    if not meeting:
        return False
    if meeting.is_cancelled:
        return False
    if meeting.proposal_status != ProposalStatus.pending_confirmation:
        return False

    # Verify this participant still needs to confirm
    from src.core.database import async_session_maker

    async with async_session_maker() as session:
        row = await session.execute(
            select(MeetingUser.accepted).where(
                MeetingUser.meeting_id == meeting_id,
                MeetingUser.user_id == user_id,
            )
        )
        accepted = row.scalar_one_or_none()
        if accepted is not None:
            return False

    from src.bot.keyboards.meeting import pending_meeting_keyboard
    from src.services.meeting.proposal_text import format_proposal_text

    proposer = await UserDAO.find_one_or_none(telegram_id=meeting.proposed_by)
    proposer_name = proposer.name if proposer and proposer.name else "Организатор"
    text = format_proposal_text(meeting, proposer_name)

    return await _send_meeting_notification(
        meeting_id=meeting_id,
        user_id=user_id,
        notification_type=notification_type,
        text=text,
        scheduled_window=scheduled_window or meeting.scheduled_at,
        reply_markup=pending_meeting_keyboard(meeting_id),
        bot=bot,
    )


async def _send_final_reminder_for_meeting(
    meeting: Meeting,
    bot: Bot,
    scheduled_window: datetime,
) -> None:
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
            f"Ссылка: {link}\n"
            "Пожалуйста, подключитесь вовремя или предложите перенос, если не сможете."
        )
        await _send_meeting_notification(
            meeting_id=meeting.id,
            user_id=p.telegram_id,
            notification_type=MeetingNotificationType.final_5min,
            text=text,
            scheduled_window=scheduled_window,
            bot=bot,
        )


async def _notify_created_async(meeting_id: int) -> None:
    async with celery_db():
        await _notify_created_inner(meeting_id)


async def _notify_created_inner(meeting_id: int) -> None:
    meeting = await _load_meeting(meeting_id)
    if not meeting:
        logger.warning("Meeting %s not found for notification", meeting_id)
        return

    bot = get_worker_bot()
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
        await _send_meeting_notification(
            meeting_id=meeting_id,
            user_id=other.telegram_id,
            notification_type=MeetingNotificationType.created,
            text=text,
            scheduled_window=meeting.scheduled_at,
            bot=bot,
        )


async def _notify_reminder_async(meeting_id: int) -> None:
    async with celery_db():
        meeting = await _load_meeting(meeting_id)
        if not meeting:
            return

        bot = get_worker_bot()
        sched = (meeting.scheduled_at or datetime.now(timezone.utc)).astimezone(
            timezone.utc
        )
        rounded_window = sched.replace(
            minute=(sched.minute // 5) * 5, second=0, microsecond=0
        )
        await _send_final_reminder_for_meeting(meeting, bot, rounded_window)


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


async def _send_confirmation_reminders_async() -> None:
    async with celery_db():
        from src.core.database import async_session_maker
        from src.utils.tz import MSK

        now = datetime.now(timezone.utc)
        # Leave a 5-minute buffer for the final reminder
        cutoff = now + timedelta(minutes=5)

        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .where(
                    Meeting.proposal_status == ProposalStatus.pending_confirmation,
                    Meeting.is_cancelled.is_(False),
                    Meeting.scheduled_at.isnot(None),
                    Meeting.scheduled_at > cutoff,
                )
                .options(joinedload(Meeting.participants))
            )
            result = await session.execute(query)
            meetings = result.unique().scalars().all()

        if not meetings:
            return

        bot = get_worker_bot()
        # Daily window for deduplication (midnight MSK)
        today = now.astimezone(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
        scheduled_window = today.astimezone(timezone.utc)

        for meeting in meetings:
            for p in meeting.participants:
                await _send_confirmation_request(
                    meeting.id,
                    p.telegram_id,
                    bot=bot,
                    scheduled_window=scheduled_window,
                    notification_type=MeetingNotificationType.reminder_repeat,
                )


@celery_app.task(name="meeting.send_confirmation_reminders", ignore_result=True)
def send_confirmation_reminders() -> None:
    try:
        run_async(_send_confirmation_reminders_async())
    except Exception:
        logger.exception("send_confirmation_reminders failed")
        raise


async def _send_final_reminders_async() -> None:
    async with celery_db():
        from src.core.database import async_session_maker

        now = datetime.now(timezone.utc)
        # Look for meetings starting in ~5 minutes
        window_start = now + timedelta(minutes=3)
        window_end = now + timedelta(minutes=8)

        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .where(
                    Meeting.is_cancelled.is_(False),
                    Meeting.scheduled_at.isnot(None),
                    Meeting.scheduled_at.between(window_start, window_end),
                )
                .options(joinedload(Meeting.participants))
            )
            result = await session.execute(query)
            meetings = result.unique().scalars().all()

        if not meetings:
            return

        bot = get_worker_bot()
        for meeting in meetings:
            # Round scheduled_at to a 5-minute bucket for idempotency
            sched = meeting.scheduled_at.astimezone(timezone.utc)
            rounded_window = sched.replace(
                minute=(sched.minute // 5) * 5, second=0, microsecond=0
            )
            await _send_final_reminder_for_meeting(meeting, bot, rounded_window)


@celery_app.task(name="meeting.send_final_reminders", ignore_result=True)
def send_final_reminders() -> None:
    try:
        run_async(_send_final_reminders_async())
    except Exception:
        logger.exception("send_final_reminders failed")
        raise


async def _archive_notion_page_async(notion_page_id: str) -> None:
    from src.services.notion_sync_v2 import sync_service_scope

    async with sync_service_scope() as sync:
        if sync is None or sync.event_repo is None:
            logger.warning(
                "No sync service available to archive page %s", notion_page_id
            )
            return
        async with celery_db():
            archived = await sync.event_repo._client.archive_page(notion_page_id)
            if archived:
                logger.info("Archived Notion page %s", notion_page_id)
            else:
                logger.warning("Failed to archive Notion page %s", notion_page_id)


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


async def _request_due_call_durations_async() -> None:
    async with celery_db():
        from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
        from src.dao.survey_session import SurveySessionDAO
        from src.dao.survey_template import SurveyTemplateDAO
        from src.services.survey_session import SurveySessionService

        template = await SurveyTemplateDAO.get_by_slug(CALL_DURATION_TEMPLATE_SLUG)
        if not template:
            logger.warning(
                "request_due_call_durations: template %s not found",
                CALL_DURATION_TEMPLATE_SLUG,
            )
            return

        now = datetime.now(timezone.utc)
        due_meetings = await MeetingDAO.find_due_call_duration_request_meetings(
            template_id=template.id,
            now=now,
        )
        if not due_meetings:
            return

        bot = get_worker_bot()
        service = SurveySessionService()
        sent = 0
        skipped = 0

        for meeting in due_meetings:
            try:
                session, already_existed = await service.create_session(
                    template_id=template.id,
                    respondent_id=meeting.mentor_telegram_id,
                    context_type=CALL_DURATION_CONTEXT_TYPE,
                    context_id=str(meeting.id),
                )
            except Exception:
                logger.exception(
                    "request_due_call_durations: failed to create session for "
                    "meeting=%s",
                    meeting.id,
                )
                continue

            if already_existed:
                skipped += 1
                continue

            await SurveySessionDAO.update_escalation_field(
                session.id, "is_escalatable", False
            )

            kb = InlineKeyboardBuilder()
            kb.button(
                text="Указать длительность",
                callback_data=StartDynamicSurveyCB(session_id=session.id),
            )
            try:
                await bot.send_message(
                    meeting.mentor_telegram_id,
                    f"⏱ Созвон #{meeting.id} идёт больше часа.\n"
                    "Укажите фактическую длительность в минутах: выберите "
                    "15/30/45/60 или отправьте число сообщением в опросе.",
                    reply_markup=kb.as_markup(),
                )
                sent += 1
            except TelegramAPIError:
                logger.warning(
                    "request_due_call_durations: failed to send survey to mentor=%s "
                    "meeting=%s",
                    meeting.mentor_telegram_id,
                    meeting.id,
                )

        logger.info(
            "request_due_call_durations: sent=%d skipped_existing=%d due=%d",
            sent,
            skipped,
            len(due_meetings),
        )


@celery_app.task(name="meeting.auto_start_due_calls", ignore_result=True)
def auto_start_due_calls() -> None:
    try:
        run_async(_auto_start_due_calls_async())
    except Exception:
        logger.exception("auto_start_due_calls failed")
        raise


@celery_app.task(name="meeting.request_due_call_durations", ignore_result=True)
def request_due_call_durations() -> None:
    try:
        run_async(_request_due_call_durations_async())
    except Exception:
        logger.exception("request_due_call_durations failed")
        raise
