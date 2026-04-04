import asyncio
import os
from typing import Callable

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state = {}


async def test_create_meeting_fsm(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Create a meeting through the full FSM dialog."""
    # Setup: mentor + mentee
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    # /menu -> Meetings
    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None, "Mentor menu should have meetings button"
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    # Click "Create meeting"
    create_btn = find_button(meetings_msg, "meeting_create")
    all_btns = get_buttons(meetings_msg)
    assert create_btn is not None, (
        f"Meetings list should have 'Create' button. "
        f"Available: {[(b.text, b.data.decode() if b.data else '') for b in all_btns]}"
    )
    create_msg = await account1.click_button(meetings_msg, text=create_btn.text)

    # Step 1: Choose student — find first student button
    student_btn = find_button(create_msg, "meeting_student:")
    assert student_btn is not None, (
        f"Should find student button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(create_msg)]}"
    )
    type_msg = await account1.click_button(create_msg, data=student_btn.data.decode())

    # Step 2: Skip meeting type
    skip_type_btn = find_button(type_msg, "meeting_skip_type")
    if skip_type_btn:
        await account1.click_button(type_msg, text=skip_type_btn.text)
    else:
        # Select first type if skip is not available
        type_btn = find_button(type_msg, "meeting_type:")
        assert type_btn is not None, "Should have type buttons"
        await account1.click_button(type_msg, text=type_btn.text)

    # Step 3: Enter description
    date_msg = await account1.send_text_in_fsm(f"[E2E-{test_run_id}] test meeting")

    # Step 4: Choose date — find first available date button
    date_btn = find_button(date_msg, "meeting_date:")
    assert date_btn is not None, (
        f"Should find date button in calendar. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(date_msg)]}"
    )
    await account1.click_button(date_msg, text=date_btn.text)

    # Step 5: Enter time as text
    link_msg = await account1.send_text_in_fsm("18:00")

    # Snapshot BEFORE step 6 — proposal is sent synchronously during finalization
    snapshot_id = await account2.snapshot_last_message_id()

    # Step 6: Skip link or enter one
    skip_link_btn = find_button(link_msg, "meeting_skip_link")
    if skip_link_btn:
        result_msg = await account1.click_button(link_msg, text=skip_link_btn.text)
    else:
        result_msg = await account1.send_text_in_fsm("https://meet.example.com/e2e")

    assert (
        "предложени" in result_msg.text.lower() or "ожидаем" in result_msg.text.lower()
    ), f"Expected 'предложени' or 'ожидаем' in response, got: {result_msg.text[:200]}"

    # DB check
    meetings = await db.get_meetings_for_mentor(ACCOUNT_1_TG_ID)
    assert len(meetings) > 0, "Should have at least one meeting"
    meeting_id = meetings[0]["id"]
    _module_state["meeting_id"] = meeting_id

    # Student confirms the proposal
    proposal_msg = await account2.wait_for_message_after(snapshot_id)
    confirm_btn = find_button(proposal_msg, "mtg_confirm:")
    assert confirm_btn is not None, (
        f"Student should receive a proposal with confirm button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(proposal_msg)]}"
    )
    confirm_result = await account2.click_button(proposal_msg, text=confirm_btn.text)
    assert "подтверждён" in confirm_result.text.lower(), (
        f"Expected 'подтверждён' in response, got: {confirm_result.text[:200]}"
    )


async def test_start_call(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """Start a call for the created meeting."""
    meeting_id = _module_state.get("meeting_id")
    assert meeting_id is not None, "Previous test must create a meeting"

    # Navigate to meetings list
    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    # Find "Start call" button for our meeting
    start_btn = find_button(meetings_msg, f"meeting_start_call:{meeting_id}")
    assert start_btn is not None, (
        f"Should find start_call button for meeting {meeting_id}. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(meetings_msg)]}"
    )
    result_msg = await account1.click_button(meetings_msg, text=start_btn.text)
    assert "начат" in result_msg.text.lower(), (
        f"Expected 'начат' in response, got: {result_msg.text[:200]}"
    )

    # DB check
    await db.assert_meeting_call_status(meeting_id, "идёт")


async def test_end_call(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """End the active call."""
    meeting_id = _module_state.get("meeting_id")
    assert meeting_id is not None, "Previous test must create a meeting"

    # Use /end_call command for simplicity
    result_msg = await account1.send_command("/end_call")
    assert result_msg.text is not None

    # DB check
    await db.assert_meeting_call_status(meeting_id, "завершён")

    meeting = await db.get_meeting(meeting_id)
    assert meeting is not None
    assert meeting["completed_at"] is not None, "completed_at should be set"


async def test_meeting_synced_to_notion(
    db: DBAssertions,
    wait_for_sync: Callable,
):
    """After meeting creation, notion_page_id should eventually appear."""
    meeting_id = _module_state.get("meeting_id")
    assert meeting_id is not None, "Previous test must create a meeting"

    result = await wait_for_sync(
        lambda: db.get_meeting_notion_page_id(meeting_id),
        max_wait=60,
        interval=3,
    )

    assert result is not None, "Meeting should have notion_page_id after sync"
