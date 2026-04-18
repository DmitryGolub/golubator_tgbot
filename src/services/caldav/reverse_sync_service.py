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
from src.services.meeting.proposal_text import format_proposal_text, format_when
from src.tasks._db import get_worker_bot
from src.utils.bot_send import safe_send_message
from src.utils.escape import e
from src.utils.time import is_past

logger = logging.getLogger(__name__)


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
        when_str = format_when(meeting.scheduled_at)
        text = (
            f"❌ Встреча {when_str} отменена — "
            f"<b>{proposer_name}</b> удалил(а) событие в своём календаре."
        )

        bot = get_worker_bot()
        notified = 0
        for participant in meeting.participants or []:
            if participant.telegram_id == source_user_id:
                continue
            if await safe_send_message(bot, participant, text):
                notified += 1

        confirmed_proposer = 0
        if source_user_id > 0 and proposer is not None:
            if await safe_send_message(
                bot, proposer, f"✅ Встреча {when_str} отменена."
            ):
                confirmed_proposer = 1

        logger.info(
            "caldav.reverse: cancel applied",
            extra={
                "meeting_id": meeting_id,
                "account_id": source_account_id,
                "notified": notified,
                "confirmed_proposer": confirmed_proposer,
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

        past = is_past(new_scheduled_at)
        if past:
            meeting = await MeetingDAO.silent_reschedule_past(
                meeting_id=meeting_id,
                new_scheduled_at=new_scheduled_at,
                proposer_id=source_user_id,
            )
        else:
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
        when_str = format_when(meeting.scheduled_at)
        notified = 0
        other_names: list[str] = []
        for participant in meeting.participants or []:
            if participant.telegram_id == source_user_id:
                continue
            other_names.append(
                participant.name if participant.name else f"id{participant.telegram_id}"
            )
            if past:
                text = (
                    f"📅 Встреча перенесена на {when_str} (прошедшее время) — "
                    f"<b>{e(proposer_name)}</b> поправил(а) время в календаре. "
                    f"Подтверждение не требуется."
                )
                delivered = await safe_send_message(bot, participant, text)
            else:
                delivered = await safe_send_message(
                    bot,
                    participant,
                    format_proposal_text(meeting, proposer_name),
                    reply_markup=pending_meeting_keyboard(meeting.id),
                )
            if delivered:
                notified += 1

        confirmed_proposer = 0
        if source_user_id > 0 and proposer is not None:
            other_label = ", ".join(other_names) if other_names else "участника"
            if past:
                proposer_text = (
                    f"✅ Время встречи обновлено на {when_str}. "
                    f"Встреча уже прошла — подтверждение не требуется."
                )
            else:
                proposer_text = (
                    f"✅ Перенос встречи на {when_str} предложен. "
                    f"Ждём подтверждения от <b>{e(other_label)}</b>."
                )
            if await safe_send_message(bot, proposer, proposer_text):
                confirmed_proposer = 1

        logger.info(
            "caldav.reverse: reschedule applied",
            extra={
                "meeting_id": meeting_id,
                "account_id": source_account_id,
                "notified": notified,
                "confirmed_proposer": confirmed_proposer,
                "past": past,
            },
        )
