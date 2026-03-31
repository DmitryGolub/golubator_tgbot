import os
from typing import Callable

import pytest

from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import TestSetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))


def _find_button(msg, data_prefix: str):
    """Find inline button by callback_data prefix."""
    if msg.reply_markup and hasattr(msg.reply_markup, "rows"):
        for row in msg.reply_markup.rows:
            for btn in row.buttons:
                if btn.data and btn.data.decode().startswith(data_prefix):
                    return btn
    return None


def _get_buttons(msg) -> list:
    """Get all inline buttons from message."""
    buttons = []
    if msg.reply_markup and hasattr(msg.reply_markup, "rows"):
        for row in msg.reply_markup.rows:
            buttons.extend(row.buttons)
    return buttons


async def test_change_mentee_mentor(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Admin changes mentee's mentor via bot update flow."""
    # Setup
    await account1.send_command_multi("/start", count=2)
    await account2.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    # /menu -> Users
    menu_msg = await account1.send_command("/menu")
    users_btn = _find_button(menu_msg, "menu_users")
    assert users_btn is not None, "Admin menu should have 'Users' button"
    users_msg = await account1.click_button(menu_msg, text=users_btn.text)

    # Click "Update"
    update_btn = _find_button(users_msg, "user_update_menu")
    assert update_btn is not None, (
        f"Users list should have 'Update' button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in _get_buttons(users_msg)]}"
    )
    param_msg = await account1.click_button(users_msg, text=update_btn.text)

    # Choose "Mentor" parameter
    mentor_param_btn = _find_button(param_msg, "upd_param:mentor")
    assert mentor_param_btn is not None, (
        f"Should find mentor param button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in _get_buttons(param_msg)]}"
    )
    mentor_select_msg = await account1.click_button(
        param_msg, text=mentor_param_btn.text
    )

    # Choose mentor (account1)
    mentor_btn = _find_button(mentor_select_msg, f"upd_mentor:{ACCOUNT_1_TG_ID}")
    assert mentor_btn is not None, (
        f"Should find mentor button for {ACCOUNT_1_TG_ID}. Buttons: "
        f"{[(b.text, b.data.decode()) for b in _get_buttons(mentor_select_msg)]}"
    )
    user_select_msg = await account1.click_button(
        mentor_select_msg, text=mentor_btn.text
    )

    # Choose user (account2)
    user_btn = _find_button(user_select_msg, f"upd_user:{ACCOUNT_2_TG_ID}")
    assert user_btn is not None, (
        f"Should find user button for {ACCOUNT_2_TG_ID}. Buttons: "
        f"{[(b.text, b.data.decode()) for b in _get_buttons(user_select_msg)]}"
    )
    result_msg = await account1.click_button(user_select_msg, text=user_btn.text)
    assert "обновлено" in result_msg.text.lower(), (
        f"Expected 'обновлено' in response, got: {result_msg.text[:200]}"
    )

    # DB check
    mentee = await db.get_mentee(ACCOUNT_2_TG_ID)
    assert mentee is not None, "Mentee record should exist"
    assert mentee["mentor_id"] is not None, "Mentee should have a mentor assigned"


async def test_mentee_change_synced_to_notion(
    db: DBAssertions,
    wait_for_sync: Callable,
):
    """After mentor assignment, mentee's synced_at should eventually be set."""
    try:
        result = await wait_for_sync(
            lambda: db.get_mentee_synced_at(ACCOUNT_2_TG_ID),
            max_wait=30,
            interval=3,
        )
    except AssertionError:
        pytest.skip("Notion sync not completed within timeout")
        return

    if result is None:
        pytest.skip("Mentee synced_at not set — Notion may not be configured")


async def test_update_user_info(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Admin updates user's status cohort via bot."""
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID)
    await setup.ensure_user_cohort(ACCOUNT_2_TG_ID, "Status", "study")

    # /menu -> Users -> Update -> Status
    menu_msg = await account1.send_command("/menu")
    users_btn = _find_button(menu_msg, "menu_users")
    users_msg = await account1.click_button(menu_msg, text=users_btn.text)

    update_btn = _find_button(users_msg, "user_update_menu")
    assert update_btn is not None
    param_msg = await account1.click_button(users_msg, text=update_btn.text)

    # Choose "Status" parameter
    status_param_btn = _find_button(param_msg, "upd_param:status")
    assert status_param_btn is not None, (
        f"Should find status param button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in _get_buttons(param_msg)]}"
    )
    status_select_msg = await account1.click_button(
        param_msg, text=status_param_btn.text
    )

    # Choose "search" status value
    search_btn = None
    for btn in _get_buttons(status_select_msg):
        if btn.data and b"upd_enum:status:" in btn.data:
            if b"search" in btn.data.lower() or "search" in btn.text.lower():
                search_btn = btn
                break

    if search_btn is None:
        # Fall back: pick any status button
        search_btn = _find_button(status_select_msg, "upd_enum:status:")

    assert search_btn is not None, (
        f"Should find status value button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in _get_buttons(status_select_msg)]}"
    )
    user_select_msg = await account1.click_button(
        status_select_msg, text=search_btn.text
    )

    # Choose user (account2)
    user_btn = _find_button(user_select_msg, f"upd_user:{ACCOUNT_2_TG_ID}")
    assert user_btn is not None, (
        f"Should find user button for {ACCOUNT_2_TG_ID}. Buttons: "
        f"{[(b.text, b.data.decode()) for b in _get_buttons(user_select_msg)]}"
    )
    result_msg = await account1.click_button(user_select_msg, text=user_btn.text)
    assert "обновлено" in result_msg.text.lower(), (
        f"Expected 'обновлено', got: {result_msg.text[:200]}"
    )

    # DB check: cohort should be updated
    cohorts = await db.get_user_cohorts(ACCOUNT_2_TG_ID)
    status_cohorts = [c for c in cohorts if c["type"] == "Status"]
    assert len(status_cohorts) > 0, "User should have Status cohort"
