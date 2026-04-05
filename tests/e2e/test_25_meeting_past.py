import asyncio
import os

import pytest

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state = {}


async def test_completed_meeting_hidden_from_main_list(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Completed meeting should not appear in the main meetings list."""
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    meeting_id = await setup.create_meeting(
        ACCOUNT_1_TG_ID,
        ACCOUNT_2_TG_ID,
        description="past-meetings-test",
        run_id=test_run_id,
    )
    _module_state["meeting_id"] = meeting_id

    # Start and finish the call
    msg = await account1.press_callback(f"meeting_start_call:{meeting_id}")
    assert "✅" in msg.text or "начат" in msg.text.lower(), (
        f"Expected successful start, got: {msg.text[:200]}"
    )
    await db.assert_meeting_call_status(meeting_id, "идёт")

    end_msg = await account1.send_command("/end_call")
    assert end_msg.text is not None
    await db.assert_meeting_call_status(meeting_id, "завершён")

    await account1.drain_messages()

    # Navigate to main meetings list
    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None, (
        f"Menu should have meetings button. Buttons: {button_labels(menu_msg)}"
    )
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    # Completed meeting should NOT be in the main list
    del_btn = find_button(meetings_msg, f"meeting_del:{meeting_id}")
    start_btn = find_button(meetings_msg, f"meeting_start_call:{meeting_id}")
    assert del_btn is None and start_btn is None, (
        f"Completed meeting {meeting_id} should not appear in main list. "
        f"Buttons: {button_labels(meetings_msg)}"
    )

    # "Завершённые созвоны" button should be present
    past_btn = find_button(meetings_msg, "past_meetings_mentor")
    assert past_btn is not None, (
        f"Should have 'past_meetings_mentor' button. Buttons: {button_labels(meetings_msg)}"
    )
    _module_state["meetings_msg"] = meetings_msg


async def test_completed_meeting_visible_in_past_submenu(
    account1: TelegramTestClient,
):
    """Completed meeting should appear in the past meetings submenu."""
    meetings_msg = _module_state.get("meetings_msg")
    meeting_id = _module_state.get("meeting_id")
    if meetings_msg is None or meeting_id is None:
        pytest.skip("prerequisite test failed")

    past_msg = await account1.click_button(meetings_msg, data="past_meetings_mentor")

    assert past_msg.text is not None
    assert "завершённые" in past_msg.text.lower(), (
        f"Expected 'Завершённые' in text, got: {past_msg.text[:200]}"
    )

    del_btn = find_button(past_msg, f"meeting_del:{meeting_id}")
    assert del_btn is not None, (
        f"Should find delete button for meeting {meeting_id} in past list. "
        f"Buttons: {button_labels(past_msg)}"
    )
    _module_state["past_msg"] = past_msg


async def test_back_from_past_to_main_meetings(
    account1: TelegramTestClient,
):
    """Back button from past submenu returns to main meetings list."""
    past_msg = _module_state.get("past_msg")
    if past_msg is None:
        pytest.skip("prerequisite test failed")

    back_btn = find_button(past_msg, "mentor_meetings_list")
    assert back_btn is not None, (
        f"Should have back button. Buttons: {button_labels(past_msg)}"
    )
    main_msg = await account1.click_button(past_msg, data="mentor_meetings_list")

    assert main_msg.text is not None
    assert "мои созвоны" in main_msg.text.lower(), (
        f"Expected 'Мои созвоны' in text, got: {main_msg.text[:200]}"
    )


async def test_student_past_meetings_submenu(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Student should see completed meetings in the past submenu."""
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await bot_setup.ensure_role_permission("student", "view_own_meetings")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    meeting_id = await setup.create_meeting(
        ACCOUNT_1_TG_ID,
        ACCOUNT_2_TG_ID,
        description="student-past-test",
        run_id=test_run_id,
    )

    # Start and finish call as mentor
    msg = await account1.press_callback(f"meeting_start_call:{meeting_id}")
    assert "✅" in msg.text or "начат" in msg.text.lower()
    await db.assert_meeting_call_status(meeting_id, "идёт")

    end_msg = await account1.send_command("/end_call")
    assert end_msg.text is not None
    await db.assert_meeting_call_status(meeting_id, "завершён")

    await account2.drain_messages()

    # Student navigates to meetings
    menu_msg = await account2.send_command("/menu")
    student_meetings_btn = find_button(menu_msg, "student_meetings")
    assert student_meetings_btn is not None, (
        f"Student menu should have 'student_meetings' button. "
        f"Buttons: {button_labels(menu_msg)}"
    )
    meetings_msg = await account2.click_button(menu_msg, text=student_meetings_btn.text)

    # Completed meeting should NOT be in the main list
    del_btn = find_button(meetings_msg, f"meeting_del:{meeting_id}")
    assert del_btn is None, (
        f"Completed meeting should not appear in student main list. "
        f"Buttons: {button_labels(meetings_msg)}"
    )

    # Navigate to past meetings
    past_btn = find_button(meetings_msg, "past_meetings_student")
    assert past_btn is not None, (
        f"Should have 'past_meetings_student' button. "
        f"Buttons: {button_labels(meetings_msg)}"
    )
    past_msg = await account2.click_button(meetings_msg, data="past_meetings_student")

    assert past_msg.text is not None
    assert "завершённые" in past_msg.text.lower(), (
        f"Expected 'Завершённые' in text, got: {past_msg.text[:200]}"
    )
