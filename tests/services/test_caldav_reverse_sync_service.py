"""Unit tests for CalDAVReverseSyncService — fully mocked."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.caldav import reverse_sync_service as rs_mod
from src.services.caldav.reverse_sync_service import CalDAVReverseSyncService


def _user(telegram_id, name="Alice", registered=True):
    return SimpleNamespace(
        telegram_id=telegram_id,
        name=name,
        username=None,
        registered_at=datetime(2025, 1, 1, tzinfo=timezone.utc) if registered else None,
    )


def _meeting(
    meeting_id=42,
    scheduled_at=None,
    participants=None,
    is_cancelled=False,
    original_scheduled_at=None,
    proposal_status=None,
):
    return SimpleNamespace(
        id=meeting_id,
        scheduled_at=scheduled_at or datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        participants=participants or [],
        is_cancelled=is_cancelled,
        meeting_link=None,
        description=None,
        original_scheduled_at=original_scheduled_at,
        proposal_status=proposal_status,
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


async def test_reschedule_past_uses_silent_dao_and_sends_nothing():
    account = SimpleNamespace(id=7, telegram_id=100)
    past_dt = datetime.now(timezone.utc) - timedelta(hours=2)
    existing = _meeting(participants=[_user(100), _user(200)])
    rescheduled = _meeting(
        scheduled_at=past_dt, participants=[_user(100, "A"), _user(200, "B")]
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
            "silent_reschedule_past",
            AsyncMock(return_value=rescheduled),
        ) as silent,
        patch.object(rs_mod.MeetingDAO, "propose_reschedule", AsyncMock()) as propose,
        patch.object(
            rs_mod.UserDAO, "find_one_or_none", AsyncMock(return_value=_user(100, "A"))
        ),
        patch.object(rs_mod, "get_worker_bot", lambda: bot),
    ):
        await CalDAVReverseSyncService().reschedule_from_caldav(
            meeting_id=42, new_scheduled_at=past_dt, source_account_id=7
        )

    silent.assert_awaited_once_with(
        meeting_id=42, new_scheduled_at=past_dt, proposer_id=100
    )
    propose.assert_not_awaited()
    # Past reschedules are applied silently — no Telegram notifications.
    bot.send_message.assert_not_awaited()


async def test_reschedule_future_autoconfirm_notifies_only_proposer():
    from src.models.meeting import ProposalStatus

    account = SimpleNamespace(id=7, telegram_id=100)
    future_dt = datetime.now(timezone.utc) + timedelta(days=1)
    existing = _meeting(participants=[_user(100), _user(-1, "Placeholder", False)])
    rescheduled = _meeting(
        scheduled_at=future_dt,
        participants=[_user(100, "A"), _user(-1, "Placeholder", False)],
        proposal_status=ProposalStatus.confirmed,
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
        ),
        patch.object(
            rs_mod.UserDAO, "find_one_or_none", AsyncMock(return_value=_user(100, "A"))
        ),
        patch.object(rs_mod, "get_worker_bot", lambda: bot),
    ):
        await CalDAVReverseSyncService().reschedule_from_caldav(
            meeting_id=42, new_scheduled_at=future_dt, source_account_id=7
        )

    # Auto-confirmed — only the proposer receives an FYI, placeholder is skipped.
    assert bot.send_message.await_count == 1
    recipients = [call.args[0] for call in bot.send_message.await_args_list]
    assert recipients == [100]
    assert "reply_markup" not in bot.send_message.await_args_list[0].kwargs


async def test_reschedule_skips_unregistered_participant():
    account = SimpleNamespace(id=7, telegram_id=100)
    future_dt = datetime.now(timezone.utc) + timedelta(days=1)
    existing = _meeting(participants=[_user(100), _user(200)])
    rescheduled = _meeting(
        scheduled_at=future_dt,
        participants=[
            _user(100, "A"),
            _user(200, "Unregistered", registered=False),
        ],
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
        ),
        patch.object(
            rs_mod.UserDAO, "find_one_or_none", AsyncMock(return_value=_user(100, "A"))
        ),
        patch.object(rs_mod, "get_worker_bot", lambda: bot),
    ):
        await CalDAVReverseSyncService().reschedule_from_caldav(
            meeting_id=42, new_scheduled_at=future_dt, source_account_id=7
        )

    # Only the proposer confirmation is sent; the unregistered participant (200)
    # is silently skipped.
    assert bot.send_message.await_count == 1
    recipients = [call.args[0] for call in bot.send_message.await_args_list]
    assert 100 in recipients
    assert 200 not in recipients


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
