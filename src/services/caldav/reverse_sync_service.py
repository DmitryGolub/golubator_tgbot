"""Apply CalDAV pull changes to the domain + notify Telegram participants.

A thin wrapper around `MeetingDAO` so the pull-service stays focused on
detecting/parsing changes while this module owns the user-visible side
effects (cancel, reschedule, bot messages).
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.bot.keyboards.meeting import pending_meeting_keyboard
from src.dao.caldav_account import CalDAVAccountDAO
from src.dao.meeting import MeetingDAO
from src.dao.user import UserDAO
from src.services.meeting.proposal_text import format_proposal_text
from src.tasks._db import get_worker_bot
from src.utils.tz import MSK

logger = logging.getLogger(__name__)


def _format_when(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    try:
        return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M MSK")
    except Exception:
        return dt.isoformat()


class CalDAVReverseSyncService:
    async def cancel_from_caldav(
        self, meeting_id: int, *, source_account_id: int
    ) -> None:
        account = await CalDAVAccountDAO.get_by_id(source_account_id)
        if account is None:
            logger.warning(
                "caldav.reverse: cancel skipped — source account not found",
                extra={"meeting_id": meeting_id, "account_id": source_account_id},
            )
            return
        source_user_id = account.telegram_id

        meeting = await MeetingDAO.cancel_by_user(
            meeting_id=meeting_id, user_id=source_user_id
        )
        if meeting is None:
            logger.info(
                "caldav.reverse: cancel — meeting not found or user not participant",
                extra={"meeting_id": meeting_id, "user_id": source_user_id},
            )
            return

        proposer = await UserDAO.find_one_or_none(telegram_id=source_user_id)
        proposer_name = (
            proposer.name if proposer and proposer.name else f"id{source_user_id}"
        )
        when_str = _format_when(meeting.scheduled_at)
        text = (
            f"❌ Встреча {when_str} отменена — "
            f"<b>{proposer_name}</b> удалил(а) событие в своём календаре."
        )

        bot = get_worker_bot()
        for participant in meeting.participants or []:
            if participant.telegram_id == source_user_id:
                continue
            if participant.telegram_id < 0:
                continue  # placeholder user — no Telegram chat
            try:
                await bot.send_message(participant.telegram_id, text)
            except Exception:
                logger.exception(
                    "caldav.reverse: failed to notify cancel",
                    extra={
                        "meeting_id": meeting_id,
                        "recipient": participant.telegram_id,
                    },
                )

    async def reschedule_from_caldav(
        self,
        meeting_id: int,
        *,
        new_scheduled_at: datetime,
        source_account_id: int,
    ) -> None:
        account = await CalDAVAccountDAO.get_by_id(source_account_id)
        if account is None:
            logger.warning(
                "caldav.reverse: reschedule skipped — source account not found",
                extra={"meeting_id": meeting_id, "account_id": source_account_id},
            )
            return
        source_user_id = account.telegram_id

        existing = await MeetingDAO.get_with_participants(meeting_id)
        if existing is None:
            logger.info(
                "caldav.reverse: reschedule — meeting not found",
                extra={"meeting_id": meeting_id},
            )
            return
        if existing.is_cancelled:
            # Pull does not resurrect cancelled meetings.
            logger.info(
                "caldav.reverse: reschedule skipped — meeting cancelled",
                extra={"meeting_id": meeting_id},
            )
            return

        meeting = await MeetingDAO.propose_reschedule(
            meeting_id=meeting_id,
            new_scheduled_at=new_scheduled_at,
            new_link=None,
            proposer_id=source_user_id,
        )
        if meeting is None:
            logger.info(
                "caldav.reverse: reschedule — meeting completed or user not participant",
                extra={"meeting_id": meeting_id, "user_id": source_user_id},
            )
            return

        proposer = await UserDAO.find_one_or_none(telegram_id=source_user_id)
        proposer_name = (
            proposer.name if proposer and proposer.name else f"id{source_user_id}"
        )

        bot = get_worker_bot()
        for participant in meeting.participants or []:
            if participant.telegram_id == source_user_id:
                continue
            if participant.telegram_id < 0:
                continue
            try:
                await bot.send_message(
                    participant.telegram_id,
                    format_proposal_text(meeting, proposer_name),
                    reply_markup=pending_meeting_keyboard(meeting.id),
                )
            except Exception:
                logger.exception(
                    "caldav.reverse: failed to notify reschedule",
                    extra={
                        "meeting_id": meeting_id,
                        "recipient": participant.telegram_id,
                    },
                )
