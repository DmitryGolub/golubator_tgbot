"""E2E tests for meeting proposal/confirmation flow (BT-9).

All tests interact with the bot via real Telegram UI using 3 accounts:
  account1 = mentor (ACCOUNT_1_TG_ID)
  account2 = student (ACCOUNT_2_TG_ID)
  account3 = admin (via bot_setup fixture)
"""

import asyncio
import os
from typing import Any

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))  # mentor
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))  # student

_state_chain_a: dict[str, Any] = {}  # shared state between A1 and A2
_state_chain_e: dict[str, Any] = {}  # shared state between E1 and E2


# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


async def _setup_mentor_student(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    bot_setup: BotSetup,
    setup: E2ESetup,
):
    """Common setup: account1=mentor, account2=student with mentee relation."""
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)


async def _create_pending_meeting_via_ui(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    test_run_id: str,
) -> tuple[int, Any]:
    """Creates a meeting proposal via mentor FSM.

    Returns (meeting_id, proposal_msg_for_account2).
    Snapshot of account2 is captured before the FSM starts.
    """
    snapshot_id = await account2.snapshot_last_message_id()

    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None, "Mentor menu should have meetings button"
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    create_btn = find_button(meetings_msg, "meeting_create")
    assert create_btn is not None, (
        f"Meetings list should have 'Create' button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(meetings_msg)]}"
    )
    create_msg = await account1.click_button(meetings_msg, text=create_btn.text)

    student_btn = find_button(create_msg, "meeting_student:")
    assert student_btn is not None, (
        f"Should find student button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(create_msg)]}"
    )
    type_msg = await account1.click_button(create_msg, data=student_btn.data.decode())

    skip_type_btn = find_button(type_msg, "meeting_skip_type")
    if skip_type_btn:
        await account1.click_button(type_msg, text=skip_type_btn.text)
    else:
        type_btn = find_button(type_msg, "meeting_type:")
        assert type_btn is not None, "Should have type buttons"
        await account1.click_button(type_msg, text=type_btn.text)

    date_msg = await account1.send_text_in_fsm(f"[E2E-{test_run_id}] proposal test")
    date_btn = find_button(date_msg, "meeting_date:")
    assert date_btn is not None, (
        f"Should find date button in calendar. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(date_msg)]}"
    )
    await account1.click_button(date_msg, text=date_btn.text)

    link_msg = await account1.send_text_in_fsm("18:00")
    skip_link_btn = find_button(link_msg, "meeting_skip_link")
    if skip_link_btn:
        result_msg = await account1.click_button(link_msg, text=skip_link_btn.text)
    else:
        result_msg = await account1.send_text_in_fsm("https://meet.example.com/e2e")

    assert (
        "предложени" in result_msg.text.lower() or "ожидаем" in result_msg.text.lower()
    ), f"Expected proposal sent message, got: {result_msg.text[:200]}"

    proposal_msg = await account2.wait_for_message_after(snapshot_id)
    meetings = await db.get_meetings_for_mentor(ACCOUNT_1_TG_ID)
    meeting_id = meetings[0]["id"]
    return meeting_id, proposal_msg


# ---------------------------------------------------------------------------
# Chain A: mentor proposes → student confirms → call
# ---------------------------------------------------------------------------


async def test_mentor_proposes_student_confirms(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """A1: Mentor creates meeting → student confirms → both notified."""
    await _setup_mentor_student(account1, account2, bot_setup, setup)

    meeting_id, proposal_msg = await _create_pending_meeting_via_ui(
        account1, account2, db, test_run_id
    )

    confirm_btn = find_button(proposal_msg, "mtg_confirm:")
    assert confirm_btn is not None, (
        f"Student proposal should have confirm button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(proposal_msg)]}"
    )

    # account1 snapshot before account2 confirms
    snap_account1 = await account1.snapshot_last_message_id()

    confirm_result = await account2.click_button(proposal_msg, text=confirm_btn.text)
    assert (
        "подтверждён" in confirm_result.text.lower()
        or "назначен" in confirm_result.text.lower()
    ), (
        f"Expected 'подтверждён' or 'назначен' in response, got: {confirm_result.text[:200]}"
    )

    # DB: proposal_status = confirmed
    await db.assert_meeting_proposal_confirmed(meeting_id)

    # account1 should receive a confirmation notification
    notif = await account1.wait_for_message_after(snap_account1)
    assert "подтверждён" in notif.text.lower(), (
        f"Mentor should get confirmation notification, got: {notif.text[:200]}"
    )

    _state_chain_a["confirmed_meeting_id"] = meeting_id


async def test_start_and_end_call_after_confirm(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """A2: After confirmation, mentor can start and end call."""
    meeting_id = _state_chain_a.get("confirmed_meeting_id")
    assert meeting_id is not None, "A1 must run first to set confirmed_meeting_id"

    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    start_btn = find_button(meetings_msg, f"meeting_start_call:{meeting_id}")
    assert start_btn is not None, (
        f"Should find start_call button for meeting {meeting_id}. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(meetings_msg)]}"
    )
    result_msg = await account1.click_button(meetings_msg, text=start_btn.text)
    assert "начат" in result_msg.text.lower(), (
        f"Expected 'начат', got: {result_msg.text[:200]}"
    )

    await db.assert_meeting_call_status(meeting_id, "идёт")

    end_msg = await account1.send_command("/end_call")
    assert end_msg.text is not None

    await db.assert_meeting_call_status(meeting_id, "завершён")


# ---------------------------------------------------------------------------
# Scenario B: mentor proposes → student declines
# ---------------------------------------------------------------------------


async def test_mentor_proposes_student_declines(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """B: Student declines proposal — meeting is deleted, mentor notified."""
    await _setup_mentor_student(account1, account2, bot_setup, setup)

    snap_account1 = await account1.snapshot_last_message_id()
    meeting_id, proposal_msg = await _create_pending_meeting_via_ui(
        account1, account2, db, test_run_id
    )
    # Re-snapshot account1 after FSM completes so notification comes after
    snap_account1 = await account1.snapshot_last_message_id()

    decline_btn = find_button(proposal_msg, "mtg_decline:")
    assert decline_btn is not None, (
        f"Student proposal should have decline button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(proposal_msg)]}"
    )
    decline_result = await account2.click_button(proposal_msg, text=decline_btn.text)
    assert "отклонен" in decline_result.text.lower(), (
        f"Expected 'отклонен' in response, got: {decline_result.text[:200]}"
    )

    await db.assert_meeting_deleted(meeting_id)

    notif = await account1.wait_for_message_after(snap_account1)
    assert "отклонен" in notif.text.lower() or "предложени" in notif.text.lower(), (
        f"Mentor should be notified of decline, got: {notif.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Scenario C: student initiates via menu
# ---------------------------------------------------------------------------


async def test_student_proposes_via_menu(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """C: Student proposes meeting via menu → mentor receives proposal."""
    await _setup_mentor_student(account1, account2, bot_setup, setup)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await bot_setup.ensure_role_permission("student", "propose_meetings")

    snap_account1 = await account1.snapshot_last_message_id()

    # Student navigates to propose meeting
    menu_msg = await account2.send_command("/menu")
    propose_btn = find_button(menu_msg, "student_propose_meeting")
    assert propose_btn is not None, (
        f"Student menu should have 'student_propose_meeting' button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(menu_msg)]}"
    )
    calendar_msg = await account2.click_button(menu_msg, text=propose_btn.text)

    # Choose date
    date_btn = find_button(calendar_msg, "meeting_date:")
    assert date_btn is not None, (
        f"Should find date button in calendar. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(calendar_msg)]}"
    )
    await account2.click_button(calendar_msg, text=date_btn.text)

    # Enter time
    link_msg = await account2.send_text_in_fsm("19:00")

    # Skip link
    skip_link_btn = find_button(link_msg, "meeting_skip_link")
    if skip_link_btn:
        result_msg = await account2.click_button(link_msg, text=skip_link_btn.text)
    else:
        result_msg = await account2.send_text_in_fsm("https://meet.example.com/e2e")

    assert (
        "предложени" in result_msg.text.lower() or "ожидаем" in result_msg.text.lower()
    ), f"Expected proposal sent message, got: {result_msg.text[:200]}"

    # Mentor receives proposal notification
    proposal_msg = await account1.wait_for_message_after(snap_account1)
    confirm_btn = find_button(proposal_msg, "mtg_confirm:")
    assert confirm_btn is not None, (
        f"Mentor proposal should have confirm button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(proposal_msg)]}"
    )

    # DB: proposed_by = student, proposal_status = pending
    meetings = await db.get_meetings_for_mentor(ACCOUNT_1_TG_ID)
    assert len(meetings) > 0, "Should have at least one meeting"
    new_meeting = meetings[0]
    assert new_meeting["proposed_by"] == ACCOUNT_2_TG_ID, (
        f"Expected proposed_by={ACCOUNT_2_TG_ID}, got: {new_meeting['proposed_by']}"
    )
    await db.assert_meeting_proposal_pending(new_meeting["id"])


# ---------------------------------------------------------------------------
# Scenario D: counter proposal (propose new time)
# ---------------------------------------------------------------------------


async def test_counter_proposal_new_time(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """D: Student proposes new time → old meeting deleted, new proposal sent to mentor."""
    await _setup_mentor_student(account1, account2, bot_setup, setup)

    old_meeting_id, proposal_msg = await _create_pending_meeting_via_ui(
        account1, account2, db, test_run_id
    )

    newtime_btn = find_button(proposal_msg, "mtg_newtime:")
    assert newtime_btn is not None, (
        f"Student proposal should have 'new time' button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(proposal_msg)]}"
    )

    snap_account1 = await account1.snapshot_last_message_id()

    # account2 clicks "Предложить другое время" → calendar shown
    calendar_msg = await account2.click_button(proposal_msg, text=newtime_btn.text)

    date_btn = find_button(calendar_msg, "meeting_date:")
    assert date_btn is not None, (
        f"Should find date button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(calendar_msg)]}"
    )
    await account2.click_button(calendar_msg, text=date_btn.text)

    link_msg = await account2.send_text_in_fsm("19:00")
    skip_link_btn = find_button(link_msg, "meeting_skip_link")
    if skip_link_btn:
        result_msg = await account2.click_button(link_msg, text=skip_link_btn.text)
    else:
        result_msg = await account2.send_text_in_fsm("https://meet.example.com/e2e")

    assert (
        "предложени" in result_msg.text.lower() or "ожидаем" in result_msg.text.lower()
    ), f"Expected proposal sent message, got: {result_msg.text[:200]}"

    # Old meeting should be deleted
    await db.assert_meeting_deleted(old_meeting_id)

    # New meeting created with proposed_by = student
    meetings = await db.get_meetings_for_mentor(ACCOUNT_1_TG_ID)
    assert len(meetings) > 0, "New meeting should exist"
    new_meeting = meetings[0]
    assert new_meeting["proposed_by"] == ACCOUNT_2_TG_ID, (
        f"Expected proposed_by={ACCOUNT_2_TG_ID}, got: {new_meeting['proposed_by']}"
    )
    await db.assert_meeting_proposal_pending(new_meeting["id"])

    # Mentor receives new proposal notification
    new_proposal_msg = await account1.wait_for_message_after(snap_account1)
    confirm_btn = find_button(new_proposal_msg, "mtg_confirm:")
    assert confirm_btn is not None, (
        f"Mentor should get new proposal with confirm button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(new_proposal_msg)]}"
    )


# ---------------------------------------------------------------------------
# Chain E: reschedule proposal → confirmation
# ---------------------------------------------------------------------------


async def test_reschedule_propose(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """E1: Confirmed meeting → mentor proposes reschedule → student receives proposal."""
    await _setup_mentor_student(account1, account2, bot_setup, setup)

    # Create meeting and have student confirm it
    meeting_id, proposal_msg = await _create_pending_meeting_via_ui(
        account1, account2, db, test_run_id
    )
    confirm_btn = find_button(proposal_msg, "mtg_confirm:")
    assert confirm_btn is not None
    await account2.click_button(proposal_msg, text=confirm_btn.text)
    await db.assert_meeting_proposal_confirmed(meeting_id)

    _state_chain_e["reschedule_meeting_id"] = meeting_id

    # account2 snapshot before reschedule proposal is sent
    snap_account2 = await account2.snapshot_last_message_id()

    # Mentor navigates to meetings and clicks "Перенести"
    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    reschedule_btn = find_button(meetings_msg, f"mtg_reschedule:{meeting_id}")
    assert reschedule_btn is not None, (
        f"Should find reschedule button for meeting {meeting_id}. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(meetings_msg)]}"
    )
    calendar_msg = await account1.click_button(meetings_msg, text=reschedule_btn.text)

    # Choose date
    date_btn = find_button(calendar_msg, "meeting_date:")
    assert date_btn is not None, (
        f"Should find date in reschedule calendar. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(calendar_msg)]}"
    )
    await account1.click_button(calendar_msg, text=date_btn.text)

    link_msg = await account1.send_text_in_fsm("20:00")
    skip_link_btn = find_button(link_msg, "meeting_skip_link")
    if skip_link_btn:
        result_msg = await account1.click_button(link_msg, text=skip_link_btn.text)
    else:
        result_msg = await account1.send_text_in_fsm("https://meet.example.com/e2e")

    assert (
        "переносе" in result_msg.text.lower()
        or "предложени" in result_msg.text.lower()
        or "ожидаем" in result_msg.text.lower()
    ), f"Expected reschedule proposal sent message, got: {result_msg.text[:200]}"

    # Student receives reschedule proposal
    reschedule_proposal_msg = await account2.wait_for_message_after(snap_account2)
    confirm_btn = find_button(reschedule_proposal_msg, "mtg_confirm:")
    assert confirm_btn is not None, (
        f"Student should receive reschedule proposal with confirm button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(reschedule_proposal_msg)]}"
    )

    # DB: pending, original_scheduled_at set
    await db.assert_meeting_proposal_pending(meeting_id)
    original_at = await db.get_meeting_original_scheduled_at(meeting_id)
    assert original_at is not None, (
        "original_scheduled_at should be set after reschedule proposal"
    )


async def test_reschedule_confirm(
    account2: TelegramTestClient,
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """E2: Student confirms reschedule → meeting confirmed, original_scheduled_at cleared."""
    meeting_id = _state_chain_e.get("reschedule_meeting_id")
    assert meeting_id is not None, "E1 must run first to set reschedule_meeting_id"

    # Find the pending reschedule proposal in student's meetings
    snap_account1 = await account1.snapshot_last_message_id()

    menu_msg = await account2.send_command("/menu")
    student_meetings_btn = find_button(menu_msg, "student_meetings")
    assert student_meetings_btn is not None, (
        f"Student menu should have 'student_meetings' button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(menu_msg)]}"
    )
    meetings_msg = await account2.click_button(menu_msg, text=student_meetings_btn.text)

    confirm_btn = find_button(meetings_msg, f"mtg_confirm:{meeting_id}")
    assert confirm_btn is not None, (
        f"Should find confirm button for reschedule of meeting {meeting_id}. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(meetings_msg)]}"
    )
    confirm_result = await account2.click_button(meetings_msg, text=confirm_btn.text)
    assert "подтверждён" in confirm_result.text.lower(), (
        f"Expected 'подтверждён', got: {confirm_result.text[:200]}"
    )

    await db.assert_meeting_proposal_confirmed(meeting_id)

    original_at = await db.get_meeting_original_scheduled_at(meeting_id)
    assert original_at is None, (
        "original_scheduled_at should be cleared after reschedule confirmation"
    )

    notif = await account1.wait_for_message_after(snap_account1)
    assert "подтверждён" in notif.text.lower(), (
        f"Mentor should get confirmation notification, got: {notif.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Scenario F: reschedule → declined → time reverts
# ---------------------------------------------------------------------------


async def test_reschedule_decline_reverts_time(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """F: Declined reschedule → meeting reverts to original scheduled_at."""
    await _setup_mentor_student(account1, account2, bot_setup, setup)

    # Create and confirm a meeting
    meeting_id, proposal_msg = await _create_pending_meeting_via_ui(
        account1, account2, db, test_run_id
    )
    confirm_btn = find_button(proposal_msg, "mtg_confirm:")
    assert confirm_btn is not None
    await account2.click_button(proposal_msg, text=confirm_btn.text)
    await db.assert_meeting_proposal_confirmed(meeting_id)

    # Record original scheduled_at
    meeting = await db.get_meeting(meeting_id)
    assert meeting is not None
    original_scheduled_at = meeting["scheduled_at"]

    # Mentor proposes reschedule with different time
    snap_account2 = await account2.snapshot_last_message_id()

    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    reschedule_btn = find_button(meetings_msg, f"mtg_reschedule:{meeting_id}")
    assert reschedule_btn is not None, (
        f"Should find reschedule button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(meetings_msg)]}"
    )
    calendar_msg = await account1.click_button(meetings_msg, text=reschedule_btn.text)

    date_btn = find_button(calendar_msg, "meeting_date:")
    assert date_btn is not None
    await account1.click_button(calendar_msg, text=date_btn.text)

    link_msg = await account1.send_text_in_fsm("20:00")
    skip_link_btn = find_button(link_msg, "meeting_skip_link")
    if skip_link_btn:
        await account1.click_button(link_msg, text=skip_link_btn.text)
    else:
        await account1.send_text_in_fsm("https://meet.example.com/e2e")

    reschedule_proposal_msg = await account2.wait_for_message_after(snap_account2)

    # account1 snapshot before decline notification
    snap_account1 = await account1.snapshot_last_message_id()

    decline_btn = find_button(reschedule_proposal_msg, "mtg_decline:")
    assert decline_btn is not None, (
        f"Reschedule proposal should have decline button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(reschedule_proposal_msg)]}"
    )
    decline_result = await account2.click_button(
        reschedule_proposal_msg, text=decline_btn.text
    )
    assert (
        "перенос отклонён" in decline_result.text.lower()
        or "отклонён" in decline_result.text.lower()
    ), f"Expected 'отклонён' in response, got: {decline_result.text[:200]}"

    # DB: meeting confirmed again, original_scheduled_at cleared, time reverted
    await db.assert_meeting_proposal_confirmed(meeting_id)
    original_at_after = await db.get_meeting_original_scheduled_at(meeting_id)
    assert original_at_after is None, (
        "original_scheduled_at should be None after decline"
    )

    reverted_meeting = await db.get_meeting(meeting_id)
    assert reverted_meeting is not None
    assert reverted_meeting["scheduled_at"] == original_scheduled_at, (
        f"scheduled_at should revert to {original_scheduled_at}, "
        f"got: {reverted_meeting['scheduled_at']}"
    )

    # Mentor notified
    notif = await account1.wait_for_message_after(snap_account1)
    assert (
        "перенос отклонён" in notif.text.lower() or "отклонён" in notif.text.lower()
    ), f"Mentor should get decline notification, got: {notif.text[:200]}"
