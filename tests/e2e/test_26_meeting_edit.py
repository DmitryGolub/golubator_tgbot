"""E2E tests for meeting edit flow.

Tests the new edit flow: mentor clicks edit button on a confirmed meeting,
chooses a field to edit, enters a new value, and the meeting is updated.
"""

import os
from datetime import datetime, timezone
from typing import Any

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))  # mentor
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))  # student

_state: dict[str, Any] = {}


async def _setup_and_create_meeting(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
) -> int:
    """Common setup: create mentor/student + confirmed meeting. Returns meeting_id."""
    import asyncio

    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    scheduled = datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
    meeting_id = await setup.create_meeting(
        mentor_telegram_id=ACCOUNT_1_TG_ID,
        student_telegram_id=ACCOUNT_2_TG_ID,
        description=f"[E2E-{test_run_id}] edit test",
        scheduled_at=scheduled,
        run_id=test_run_id,
    )
    return meeting_id


async def _navigate_to_edit(
    account1: TelegramTestClient,
    meeting_id: int,
) -> Any:
    """Navigate mentor to edit menu for a specific meeting. Returns the edit menu message."""
    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None, "Mentor menu should have meetings button"
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    edit_btn = find_button(meetings_msg, f"mtg_edit:{meeting_id}")
    assert edit_btn is not None, (
        f"Should find edit button for meeting {meeting_id}. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(meetings_msg)]}"
    )
    edit_msg = await account1.click_button(meetings_msg, text=edit_btn.text)
    assert "редактирование" in edit_msg.text.lower(), (
        f"Expected edit header, got: {edit_msg.text[:200]}"
    )
    return edit_msg


async def test_edit_description(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Mentor edits meeting description."""
    meeting_id = await _setup_and_create_meeting(
        account1, account2, db, setup, bot_setup, test_run_id
    )
    _state["meeting_id"] = meeting_id

    edit_msg = await _navigate_to_edit(account1, meeting_id)

    desc_btn = find_button(edit_msg, "mtg_edit_field:description")
    assert desc_btn is not None
    await account1.click_button(edit_msg, text=desc_btn.text)

    new_desc = f"[E2E-{test_run_id}] updated description"
    result_msg = await account1.send_text_in_fsm(new_desc)
    assert "обновлён" in result_msg.text.lower(), (
        f"Expected 'обновлён', got: {result_msg.text[:200]}"
    )

    meeting = await db.get_meeting(meeting_id)
    assert meeting is not None
    assert meeting["description"] == new_desc, (
        f"Description should be updated, got: {meeting['description']}"
    )


async def test_edit_link(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Mentor edits meeting link."""
    meeting_id = _state.get("meeting_id")
    if not meeting_id:
        meeting_id = await _setup_and_create_meeting(
            account1, account2, db, setup, bot_setup, test_run_id
        )

    edit_msg = await _navigate_to_edit(account1, meeting_id)

    link_btn = find_button(edit_msg, "mtg_edit_field:link")
    assert link_btn is not None
    await account1.click_button(edit_msg, text=link_btn.text)

    new_link = "https://meet.example.com/e2e-edit"
    result_msg = await account1.send_text_in_fsm(new_link)
    assert "обновлён" in result_msg.text.lower(), (
        f"Expected 'обновлён', got: {result_msg.text[:200]}"
    )

    meeting = await db.get_meeting(meeting_id)
    assert meeting is not None
    assert meeting["meeting_link"] == new_link, (
        f"Link should be updated, got: {meeting['meeting_link']}"
    )


async def test_edit_type(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Mentor edits meeting type."""
    meeting_id = _state.get("meeting_id")
    if not meeting_id:
        meeting_id = await _setup_and_create_meeting(
            account1, account2, db, setup, bot_setup, test_run_id
        )

    edit_msg = await _navigate_to_edit(account1, meeting_id)

    type_btn = find_button(edit_msg, "mtg_edit_field:type")
    assert type_btn is not None
    await account1.click_button(edit_msg, text=type_btn.text)

    # Choose first available meeting type
    type_choice_btn = find_button(edit_msg, "meeting_type:")
    if not type_choice_btn:
        # Re-read the latest message
        menu_msg = await account1.send_command("/menu")
        meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
        meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)
        edit_btn = find_button(meetings_msg, f"mtg_edit:{meeting_id}")
        edit_msg2 = await account1.click_button(meetings_msg, text=edit_btn.text)
        type_btn2 = find_button(edit_msg2, "mtg_edit_field:type")
        type_msg = await account1.click_button(edit_msg2, text=type_btn2.text)
        type_choice_btn = find_button(type_msg, "meeting_type:")

    assert type_choice_btn is not None, "Should find meeting type button"
    result_msg = await account1.click_button(type_msg, text=type_choice_btn.text)
    assert "обновлён" in result_msg.text.lower(), (
        f"Expected 'обновлён', got: {result_msg.text[:200]}"
    )


async def test_edit_datetime(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Mentor edits meeting date/time."""
    meeting_id = _state.get("meeting_id")
    if not meeting_id:
        meeting_id = await _setup_and_create_meeting(
            account1, account2, db, setup, bot_setup, test_run_id
        )

    meeting_before = await db.get_meeting(meeting_id)
    old_scheduled_at = meeting_before["scheduled_at"]

    snap_account2 = await account2.snapshot_last_message_id()

    edit_msg = await _navigate_to_edit(account1, meeting_id)

    dt_btn = find_button(edit_msg, "mtg_edit_field:datetime")
    assert dt_btn is not None
    calendar_msg = await account1.click_button(edit_msg, text=dt_btn.text)

    date_btn = find_button(calendar_msg, "meeting_date:")
    assert date_btn is not None, (
        f"Should find date in calendar. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(calendar_msg)]}"
    )
    await account1.click_button(calendar_msg, text=date_btn.text)

    result_msg = await account1.send_text_in_fsm("19:00")
    assert "обновлён" in result_msg.text.lower(), (
        f"Expected 'обновлён', got: {result_msg.text[:200]}"
    )

    meeting_after = await db.get_meeting(meeting_id)
    assert meeting_after is not None
    assert meeting_after["scheduled_at"] != old_scheduled_at, (
        "scheduled_at should have changed after datetime edit"
    )

    # Student should receive notification
    notif = await account2.wait_for_message_after(snap_account2)
    assert "изменил" in notif.text.lower() or "созвон" in notif.text.lower(), (
        f"Student should get edit notification, got: {notif.text[:200]}"
    )


async def test_edit_cancel_at_field_selection(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Cancel at field selection stage returns to menu."""
    meeting_id = _state.get("meeting_id")
    if not meeting_id:
        meeting_id = await _setup_and_create_meeting(
            account1, account2, db, setup, bot_setup, test_run_id
        )

    edit_msg = await _navigate_to_edit(account1, meeting_id)

    cancel_btn = find_button(edit_msg, "meeting_create_cancel")
    assert cancel_btn is not None, "Should have cancel button in edit menu"
    result_msg = await account1.click_button(edit_msg, text=cancel_btn.text)
    assert "отменено" in result_msg.text.lower(), (
        f"Expected 'отменено', got: {result_msg.text[:200]}"
    )


async def test_edit_cancel_at_value_input(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """Cancel at value input stage returns to menu without changes."""
    meeting_id = _state.get("meeting_id")
    if not meeting_id:
        meeting_id = await _setup_and_create_meeting(
            account1, account2, db, setup, bot_setup, test_run_id
        )

    meeting_before = await db.get_meeting(meeting_id)

    edit_msg = await _navigate_to_edit(account1, meeting_id)

    desc_btn = find_button(edit_msg, "mtg_edit_field:description")
    assert desc_btn is not None
    input_msg = await account1.click_button(edit_msg, text=desc_btn.text)

    cancel_btn = find_button(input_msg, "meeting_create_cancel")
    assert cancel_btn is not None, "Should have cancel button during value input"
    result_msg = await account1.click_button(input_msg, text=cancel_btn.text)
    assert "отменено" in result_msg.text.lower(), (
        f"Expected 'отменено', got: {result_msg.text[:200]}"
    )

    meeting_after = await db.get_meeting(meeting_id)
    assert meeting_after["description"] == meeting_before["description"], (
        "Description should not change after cancel"
    )
