import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))


async def test_user_list_pagination(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Create enough users to trigger pagination, then navigate pages."""
    await account1.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Create 10 fake users to exceed default page size (6)
    await setup.create_fake_users(10)

    # Navigate: /menu -> Users -> Update -> Role (shows user list with pagination)
    menu_msg = await account1.send_command("/menu")
    users_btn = find_button(menu_msg, "menu_users")
    assert users_btn is not None, (
        f"Admin menu should have users button. Buttons: {button_labels(menu_msg)}"
    )
    users_msg = await account1.click_button(menu_msg, text=users_btn.text)

    update_btn = find_button(users_msg, "user_update_menu")
    assert update_btn is not None, (
        f"Users menu should have update button. Buttons: {button_labels(users_msg)}"
    )
    param_msg = await account1.click_button(users_msg, text=update_btn.text)

    # Choose "Role" param to get a list of users
    role_param_btn = find_button(param_msg, "upd_param:role")
    assert role_param_btn is not None, (
        f"Should find role param button. Buttons: {button_labels(param_msg)}"
    )
    roles_msg = await account1.click_button(param_msg, text=role_param_btn.text)

    # Choose any role value
    role_btn = find_button(roles_msg, "upd_enum:role:")
    assert role_btn is not None, (
        f"Should find role value button. Buttons: {button_labels(roles_msg)}"
    )
    users_list_msg = await account1.click_button(roles_msg, text=role_btn.text)

    # Check for pagination: look for page:users: button
    page_btn = find_button(users_list_msg, "page:users:")
    if page_btn is None:
        # May not paginate if users are less than page_size
        buttons = get_buttons(users_list_msg)
        user_buttons = [
            b for b in buttons if b.data and b.data.decode().startswith("upd_user:")
        ]
        assert len(user_buttons) < 6, (
            f"Expected pagination with {len(user_buttons)} users but no page button found. "
            f"Buttons: {button_labels(users_list_msg)}"
        )
        # Less than page_size users in this role — pagination not expected, test passes
        return

    # Navigate to page 2
    page2_msg = await account1.click_button(users_list_msg, data=page_btn.data.decode())

    # Page 2 should show different content
    page1_buttons = [
        b.data.decode()
        for b in get_buttons(users_list_msg)
        if b.data and b.data.decode().startswith("upd_user:")
    ]
    page2_buttons = [
        b.data.decode()
        for b in get_buttons(page2_msg)
        if b.data and b.data.decode().startswith("upd_user:")
    ]

    assert page2_buttons, "Page 2 should have user buttons"
    assert page1_buttons != page2_buttons, (
        "Page 1 and page 2 should show different users"
    )
