"""Unit tests for CalDAVReverseSyncService — fully mocked."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.caldav import reverse_sync_service as rs_mod
from src.services.caldav.reverse_sync_service import CalDAVReverseSyncService


def _user(telegram_id, name="Alice"):
    return SimpleNamespace(telegram_id=telegram_id, name=name, username=None)


def _meeting(meeting_id=42, scheduled_at=None, participants=None, is_cancelled=False):
    return SimpleNamespace(
        id=meeting_id,
        scheduled_at=scheduled_at or datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        participants=participants or [],
        is_cancelled=is_cancelled,
        meeting_link=None,
        description=None,
    )


async def test_cancel_from_caldav_calls_dao_and_notifies():
    account = SimpleNamespace(id=7, telegram_id=100)
    meeting = _meeting(participants=[_user(100, "A"), _user(200, "B")])
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch.object(
            rs_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(
            rs_mod.MeetingDAO, "cancel_by_user", AsyncMock(return_value=meeting)
        ) as cancel,
        patch.object(
            rs_mod.UserDAO, "find_one_or_none", AsyncMock(return_value=_user(100, "A"))
        ),
        patch.object(rs_mod, "get_worker_bot", lambda: bot),
    ):
        await CalDAVReverseSyncService().cancel_from_caldav(
            meeting_id=42, source_account_id=7
        )

    cancel.assert_awaited_once_with(meeting_id=42, user_id=100)
    # One notification for the other participant + one confirmation for the proposer.
    assert bot.send_message.await_count == 2
    recipients = [call.args[0] for call in bot.send_message.await_args_list]
    assert 200 in recipients  # the other participant
    assert 100 in recipients  # proposer receives a confirmation


async def test_cancel_skips_when_meeting_missing():
    account = SimpleNamespace(id=7, telegram_id=100)
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch.object(
            rs_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(rs_mod.MeetingDAO, "cancel_by_user", AsyncMock(return_value=None)),
        patch.object(rs_mod, "get_worker_bot", lambda: bot),
    ):
        await CalDAVReverseSyncService().cancel_from_caldav(
            meeting_id=42, source_account_id=7
        )

    bot.send_message.assert_not_awaited()


async def test_reschedule_from_caldav_calls_propose_and_notifies():
    account = SimpleNamespace(id=7, telegram_id=100)
    new_dt = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
    existing = _meeting(participants=[_user(100), _user(200)])
    rescheduled = _meeting(
        scheduled_at=new_dt, participants=[_user(100, "A"), _user(200, "B")]
    )
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch.object(
            rs_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(
            rs_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=existing),
        ),
        patch.object(
            rs_mod.MeetingDAO,
            "propose_reschedule",
            AsyncMock(return_value=rescheduled),
        ) as propose,
        patch.object(
            rs_mod.UserDAO, "find_one_or_none", AsyncMock(return_value=_user(100, "A"))
        ),
        patch.object(rs_mod, "get_worker_bot", lambda: bot),
    ):
        await CalDAVReverseSyncService().reschedule_from_caldav(
            meeting_id=42, new_scheduled_at=new_dt, source_account_id=7
        )

    propose.assert_awaited_once_with(
        meeting_id=42, new_scheduled_at=new_dt, new_link=None, proposer_id=100
    )
    # One proposal to the other participant + one confirmation to the proposer.
    assert bot.send_message.await_count == 2
    calls_by_recipient = {
        call.args[0]: call for call in bot.send_message.await_args_list
    }
    assert 200 in calls_by_recipient  # other participant
    assert 100 in calls_by_recipient  # proposer confirmation
    # The proposal (sent to the OTHER participant) carries the inline keyboard.
    assert "reply_markup" in calls_by_recipient[200].kwargs
    # The proposer confirmation is plain text (no keyboard).
    assert "reply_markup" not in calls_by_recipient[100].kwargs


async def test_reschedule_skipped_for_cancelled_meeting():
    account = SimpleNamespace(id=7, telegram_id=100)
    cancelled = _meeting(is_cancelled=True, participants=[_user(100)])
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch.object(
            rs_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(
            rs_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=cancelled),
        ),
        patch.object(rs_mod.MeetingDAO, "propose_reschedule", AsyncMock()) as propose,
        patch.object(rs_mod, "get_worker_bot", lambda: bot),
    ):
        await CalDAVReverseSyncService().reschedule_from_caldav(
            meeting_id=42,
            new_scheduled_at=datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc),
            source_account_id=7,
        )

    propose.assert_not_awaited()
    bot.send_message.assert_not_awaited()


async def test_cancel_skips_placeholder_users():
    account = SimpleNamespace(id=7, telegram_id=100)
    meeting = _meeting(
        participants=[_user(100, "A"), _user(-1, "Placeholder"), _user(200, "B")]
    )
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with (
        patch.object(
            rs_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(
            rs_mod.MeetingDAO, "cancel_by_user", AsyncMock(return_value=meeting)
        ),
        patch.object(
            rs_mod.UserDAO, "find_one_or_none", AsyncMock(return_value=_user(100, "A"))
        ),
        patch.object(rs_mod, "get_worker_bot", lambda: bot),
    ):
        await CalDAVReverseSyncService().cancel_from_caldav(
            meeting_id=42, source_account_id=7
        )

    # Real participant (200) + proposer confirmation (100); placeholder (-1) skipped.
    assert bot.send_message.await_count == 2
    recipients = [call.args[0] for call in bot.send_message.await_args_list]
    assert 200 in recipients
    assert 100 in recipients
    assert -1 not in recipients
