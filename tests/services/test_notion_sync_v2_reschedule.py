"""Unit tests for `NotionSyncServiceV2._apply_notion_reschedule`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.meeting import ProposalStatus
from src.services.notion_sync_v2 import NotionSyncServiceV2


def _user(telegram_id, name="Alice", registered=True):
    return SimpleNamespace(
        telegram_id=telegram_id,
        name=name,
        username=None,
        registered_at=datetime(2025, 1, 1, tzinfo=timezone.utc) if registered else None,
    )


def _meeting(
    *,
    meeting_id=42,
    scheduled_at=None,
    participants=None,
    is_cancelled=False,
    mentor_telegram_id=100,
    proposal_status=None,
    original_scheduled_at=None,
):
    return SimpleNamespace(
        id=meeting_id,
        scheduled_at=scheduled_at or datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        participants=participants or [],
        is_cancelled=is_cancelled,
        mentor_telegram_id=mentor_telegram_id,
        meeting_link=None,
        description=None,
        proposal_status=proposal_status,
        original_scheduled_at=original_scheduled_at,
    )


def _service():
    return NotionSyncServiceV2(mentor_repo=None, mentee_repo=None, event_repo=None)


async def test_past_move_dispatched_silently():
    past_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    existing = _meeting(participants=[_user(100), _user(200)])
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch(
            "src.dao.meeting.MeetingDAO.get_with_participants",
            AsyncMock(return_value=existing),
        ),
        patch(
            "src.dao.meeting.MeetingDAO.silent_reschedule_past",
            AsyncMock(return_value=existing),
        ) as silent,
        patch("src.dao.meeting.MeetingDAO.propose_reschedule", AsyncMock()) as propose,
        patch("src.tasks._db.get_worker_bot", lambda: bot),
    ):
        await _service()._apply_notion_reschedule(42, past_dt)

    silent.assert_awaited_once_with(
        meeting_id=42, new_scheduled_at=past_dt, proposer_id=100
    )
    propose.assert_not_awaited()
    bot.send_message.assert_not_awaited()


async def test_future_autoconfirm_only_notifies_proposer():
    future_dt = datetime.now(timezone.utc) + timedelta(days=1)
    existing = _meeting(
        participants=[_user(100, "Mentor"), _user(-1, "Placeholder", registered=False)]
    )
    rescheduled = _meeting(
        scheduled_at=future_dt,
        participants=[_user(100, "Mentor"), _user(-1, "Placeholder", registered=False)],
        proposal_status=ProposalStatus.confirmed,
    )
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch(
            "src.dao.meeting.MeetingDAO.get_with_participants",
            AsyncMock(return_value=existing),
        ),
        patch(
            "src.dao.meeting.MeetingDAO.propose_reschedule",
            AsyncMock(return_value=rescheduled),
        ) as propose,
        patch(
            "src.dao.meeting.MeetingDAO.silent_reschedule_past", AsyncMock()
        ) as silent,
        patch(
            "src.dao.user.UserDAO.find_one_or_none",
            AsyncMock(return_value=_user(100, "Mentor")),
        ),
        patch("src.tasks._db.get_worker_bot", lambda: bot),
    ):
        await _service()._apply_notion_reschedule(42, future_dt)

    propose.assert_awaited_once_with(
        meeting_id=42, new_scheduled_at=future_dt, new_link=None, proposer_id=100
    )
    silent.assert_not_awaited()
    assert bot.send_message.await_count == 1
    recipients = [c.args[0] for c in bot.send_message.await_args_list]
    assert recipients == [100]


async def test_future_pending_notifies_real_participants():
    future_dt = datetime.now(timezone.utc) + timedelta(days=1)
    existing = _meeting(participants=[_user(100), _user(200)])
    rescheduled = _meeting(
        scheduled_at=future_dt,
        participants=[_user(100, "Mentor"), _user(200, "Real")],
        proposal_status=ProposalStatus.pending_confirmation,
        original_scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch(
            "src.dao.meeting.MeetingDAO.get_with_participants",
            AsyncMock(return_value=existing),
        ),
        patch(
            "src.dao.meeting.MeetingDAO.propose_reschedule",
            AsyncMock(return_value=rescheduled),
        ),
        patch(
            "src.dao.user.UserDAO.find_one_or_none",
            AsyncMock(return_value=_user(100, "Mentor")),
        ),
        patch("src.tasks._db.get_worker_bot", lambda: bot),
    ):
        await _service()._apply_notion_reschedule(42, future_dt)

    assert bot.send_message.await_count == 2
    calls = {c.args[0]: c for c in bot.send_message.await_args_list}
    assert 200 in calls and 100 in calls
    assert "reply_markup" in calls[200].kwargs
    assert "reply_markup" not in calls[100].kwargs


async def test_cancelled_meeting_skipped():
    future_dt = datetime.now(timezone.utc) + timedelta(days=1)
    existing = _meeting(is_cancelled=True, participants=[_user(100)])
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch(
            "src.dao.meeting.MeetingDAO.get_with_participants",
            AsyncMock(return_value=existing),
        ),
        patch("src.dao.meeting.MeetingDAO.propose_reschedule", AsyncMock()) as propose,
        patch(
            "src.dao.meeting.MeetingDAO.silent_reschedule_past", AsyncMock()
        ) as silent,
        patch("src.tasks._db.get_worker_bot", lambda: bot),
    ):
        await _service()._apply_notion_reschedule(42, future_dt)

    propose.assert_not_awaited()
    silent.assert_not_awaited()
    bot.send_message.assert_not_awaited()
