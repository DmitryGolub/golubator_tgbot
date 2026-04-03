import os

from tests.e2e.helpers.buttons import find_button, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import TestSetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state = {}


async def test_delete_meeting(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Delete a meeting through the bot UI."""
    # Setup
    await account1.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    meeting_id = await setup.create_meeting(
        ACCOUNT_1_TG_ID, ACCOUNT_2_TG_ID, "E2E delete test"
    )
    _module_state["deleted_meeting_id"] = meeting_id

    # Navigate: /menu -> meetings
    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None, (
        f"Menu should have meetings button. Buttons: {button_labels(menu_msg)}"
    )
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    # Find delete button for our meeting
    del_btn = find_button(meetings_msg, f"meeting_del:{meeting_id}")
    assert del_btn is not None, (
        f"Should find delete button for meeting {meeting_id}. "
        f"Buttons: {button_labels(meetings_msg)}"
    )
    result_msg = await account1.click_button(meetings_msg, text=del_btn.text)
    assert "удалён" in result_msg.text.lower(), (
        f"Expected 'удалён' in response, got: {result_msg.text[:200]}"
    )

    # DB check
    await db.assert_meeting_deleted(meeting_id)


async def test_student_views_meetings(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Student views their meetings list."""
    # Setup
    await account2.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await setup.ensure_role_permission("student", "view_own_meetings")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    # Create a meeting so student has something to see
    await setup.create_meeting(
        ACCOUNT_1_TG_ID, ACCOUNT_2_TG_ID, "E2E student view test"
    )

    # Student navigates: /menu -> student_meetings
    menu_msg = await account2.send_command("/menu")
    student_meetings_btn = find_button(menu_msg, "student_meetings")
    assert student_meetings_btn is not None, (
        f"Student menu should have 'student_meetings' button. "
        f"Buttons: {button_labels(menu_msg)}"
    )
    meetings_msg = await account2.click_button(menu_msg, text=student_meetings_btn.text)

    # Should show meetings text (not empty)
    assert meetings_msg.text is not None, "Response should have text"
    # The meetings list should mention something about meetings
    text_lower = meetings_msg.text.lower()
    assert "созвон" in text_lower or "встреч" in text_lower or "нет" in text_lower, (
        f"Expected meetings-related text, got: {meetings_msg.text[:200]}"
    )
