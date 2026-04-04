import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state = {}


async def test_delete_meeting(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Delete a meeting through the bot UI."""
    # Setup
    await account1.send_command_multi("/start", count=2)
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    meeting_id = await bot_setup.create_meeting(
        mentor_client=account1,
        mentor_telegram_id=ACCOUNT_1_TG_ID,
        student_client=account2,
        student_telegram_id=ACCOUNT_2_TG_ID,
        description=f"[E2E-{test_run_id}] delete test",
    )
    _module_state["deleted_meeting_id"] = meeting_id
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

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
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Student views their meetings list."""
    # Setup
    await account1.send_command_multi("/start", count=2)
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await bot_setup.ensure_role_permission("student", "view_own_meetings")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    # Create a meeting so student has something to see
    await bot_setup.create_meeting(
        mentor_client=account1,
        mentor_telegram_id=ACCOUNT_1_TG_ID,
        student_client=account2,
        student_telegram_id=ACCOUNT_2_TG_ID,
        description=f"[E2E-{test_run_id}] student view test",
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


async def test_start_second_call_blocked(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Starting a second call while one is active returns an error."""
    await account1.send_command_multi("/start", count=2)
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    m1 = await setup.create_meeting(
        ACCOUNT_1_TG_ID, ACCOUNT_2_TG_ID, description="call-block-1"
    )
    m2 = await setup.create_meeting(
        ACCOUNT_1_TG_ID, ACCOUNT_2_TG_ID, description="call-block-2"
    )
    _module_state["call_block_m1"] = m1
    _module_state["call_block_m2"] = m2

    # Start first call
    msg = await account1.press_callback(f"meeting_start_call:{m1}")
    assert "✅" in msg.text or "начат" in msg.text.lower(), (
        f"Expected successful start, got: {msg.text[:200]}"
    )
    await db.assert_meeting_call_status(m1, "идёт")

    # Try to start second call — must fail with active call error
    msg2 = await account1.press_callback(f"meeting_start_call:{m2}")
    assert "активный созвон" in msg2.text.lower(), (
        f"Expected active call error, got: {msg2.text[:200]}"
    )
    row = await db._pool.fetchrow(
        "SELECT call_status FROM meetings.meetings WHERE id = $1", m2
    )
    assert row["call_status"] is None, (
        f"m2 should not be active, got: {row['call_status']}"
    )


async def test_end_call_then_start_new(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """After ending the active call, a new one can be started successfully."""
    m1 = _module_state["call_block_m1"]
    m2 = _module_state["call_block_m2"]

    # End the first call
    end_msg = await account1.send_command("/end_call")
    assert end_msg.text is not None, "Expected response from /end_call"
    await db.assert_meeting_call_status(m1, "завершён")

    # Start second call — should succeed now
    msg3 = await account1.press_callback(f"meeting_start_call:{m2}")
    assert "✅" in msg3.text or "начат" in msg3.text.lower(), (
        f"Expected successful start, got: {msg3.text[:200]}"
    )
    await db.assert_meeting_call_status(m2, "идёт")
