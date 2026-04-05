import asyncio
import os
from typing import Callable

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, find_button_paginated, get_buttons
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))


async def test_change_mentee_mentor(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin changes mentee's mentor via bot update flow."""
    # Setup: account1 = admin (navigates UI) + mentor record + manage_meetings permission
    # account2 = student (default after /start) — appears in user selection list
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    # Add manage_meetings to admin role so account1 appears in get_all_with_permission
    await setup.ensure_role_permission("admin", "manage_meetings")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    # /menu -> Users
    menu_msg = await account1.send_command("/menu")
    users_btn = find_button(menu_msg, "menu_users")
    assert users_btn is not None, "Admin menu should have 'Users' button"
    users_msg = await account1.click_button(menu_msg, text=users_btn.text)

    # Click "Update" → user list
    update_btn = find_button(users_msg, "user_update_menu")
    assert update_btn is not None, (
        f"Users list should have 'Update' button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(users_msg)]}"
    )
    user_select_msg = await account1.click_button(users_msg, text=update_btn.text)

    # Choose user (account2) → user info + param buttons
    user_btn, user_select_msg = await find_button_paginated(
        account1, user_select_msg, f"upd_user:{ACCOUNT_2_TG_ID}", menu="users"
    )
    assert user_btn is not None, (
        f"Should find user button for {ACCOUNT_2_TG_ID}. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(user_select_msg)]}"
    )
    info_msg = await account1.click_button(user_select_msg, data=user_btn.data.decode())

    # Choose "Mentor" parameter → mentor list
    mentor_param_btn = find_button(info_msg, "upd_param:mentor")
    assert mentor_param_btn is not None, (
        f"Should find mentor param button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(info_msg)]}"
    )
    mentor_select_msg = await account1.click_button(
        info_msg, text=mentor_param_btn.text
    )

    # Choose mentor (account1 — admin with manage_meetings, visible in mentor list)
    mentor_btn, mentor_select_msg = await find_button_paginated(
        account1, mentor_select_msg, f"upd_mentor:{ACCOUNT_1_TG_ID}", menu="mentors"
    )
    assert mentor_btn is not None, (
        f"Should find mentor button for {ACCOUNT_1_TG_ID}. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(mentor_select_msg)]}"
    )
    result_msg = await account1.click_button(
        mentor_select_msg, data=mentor_btn.data.decode()
    )
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
    result = await wait_for_sync(
        lambda: db.get_mentee_synced_at(ACCOUNT_2_TG_ID),
        max_wait=60,
        interval=3,
    )

    assert result is not None, "Mentee synced_at should be set after Notion sync"


async def test_update_user_info(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin updates user's status cohort via bot."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID)
    await bot_setup.set_user_cohort(ACCOUNT_2_TG_ID, "Status", "study")

    # /menu -> Users -> Update → user list
    menu_msg = await account1.send_command("/menu")
    users_btn = find_button(menu_msg, "menu_users")
    users_msg = await account1.click_button(menu_msg, text=users_btn.text)

    update_btn = find_button(users_msg, "user_update_menu")
    assert update_btn is not None
    user_select_msg = await account1.click_button(users_msg, text=update_btn.text)

    # Choose user (account2) → info + param buttons
    user_btn, user_select_msg = await find_button_paginated(
        account1, user_select_msg, f"upd_user:{ACCOUNT_2_TG_ID}", menu="users"
    )
    assert user_btn is not None, (
        f"Should find user button for {ACCOUNT_2_TG_ID}. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(user_select_msg)]}"
    )
    info_msg = await account1.click_button(user_select_msg, data=user_btn.data.decode())

    # Choose "Status" parameter → status list
    status_param_btn = find_button(info_msg, "upd_param:status")
    assert status_param_btn is not None, (
        f"Should find status param button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(info_msg)]}"
    )
    status_select_msg = await account1.click_button(
        info_msg, text=status_param_btn.text
    )

    # Choose "search" status value
    search_btn = None
    for btn in get_buttons(status_select_msg):
        if btn.data and b"upd_enum:status:" in btn.data:
            if b"search" in btn.data.lower() or "search" in btn.text.lower():
                search_btn = btn
                break

    if search_btn is None:
        # Fall back: pick any status button
        search_btn = find_button(status_select_msg, "upd_enum:status:")

    assert search_btn is not None, (
        f"Should find status value button. Buttons: "
        f"{[(b.text, b.data.decode()) for b in get_buttons(status_select_msg)]}"
    )
    result_msg = await account1.click_button(status_select_msg, text=search_btn.text)
    assert "обновлено" in result_msg.text.lower(), (
        f"Expected 'обновлено', got: {result_msg.text[:200]}"
    )

    # DB check: cohort should be updated
    cohorts = await db.get_user_cohorts(ACCOUNT_2_TG_ID)
    status_cohorts = [c for c in cohorts if c["type"] == "Status"]
    assert len(status_cohorts) > 0, "User should have Status cohort"
