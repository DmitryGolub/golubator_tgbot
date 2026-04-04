import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))

_module_state = {}


async def _navigate_to_roles(account: TelegramTestClient):
    """Navigate /menu -> Roles list."""
    menu_msg = await account.send_command("/menu")
    roles_btn = find_button(menu_msg, "menu_roles")
    assert roles_btn is not None, (
        f"Admin menu should have roles button. Buttons: {button_labels(menu_msg)}"
    )
    return await account.click_button(menu_msg, text=roles_btn.text)


async def test_edit_permissions_via_bot(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Toggle a permission on a role via bot UI."""
    await account1.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Create a dedicated test role to avoid mutating admin permissions
    test_role_id = await bot_setup.create_test_role_with_perms(
        "e2e_perm_test",
        "E2E Perm Test",
        ["view_students", "view_own_info"],
    )
    _module_state["test_role_id"] = test_role_id

    roles_msg = await _navigate_to_roles(account1)

    # Find the test role button
    role_btn = find_button(roles_msg, f"rbac_role:{test_role_id}")
    assert role_btn is not None, (
        f"Should find test role button. Buttons: {button_labels(roles_msg)}"
    )
    role_id = test_role_id
    detail_msg = await account1.click_button(roles_msg, text=role_btn.text)

    # Click "Edit permissions"
    edit_perms_btn = find_button(detail_msg, f"rbac_edit_perms:{role_id}")
    assert edit_perms_btn is not None, (
        f"Should find edit_perms button. Buttons: {button_labels(detail_msg)}"
    )
    perms_msg = await account1.click_button(detail_msg, text=edit_perms_btn.text)

    # Toggle first permission
    perm_btn = find_button(perms_msg, "rbac_perm:")
    assert perm_btn is not None, (
        f"Should find permission toggle button. Buttons: {button_labels(perms_msg)}"
    )

    # Record current state
    perms_before = await db.get_role_permissions(role_id)
    perm_ids_before = {p["id"] for p in perms_before}

    # Toggle
    await account1.click_button(perms_msg, data=perm_btn.data.decode())

    # Check DB: permission count should have changed
    perms_after = await db.get_role_permissions(role_id)
    perm_ids_after = {p["id"] for p in perms_after}
    assert perm_ids_before != perm_ids_after, (
        "Permission set should change after toggle"
    )


async def test_delete_role_with_users_prevented(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Attempting to delete a role that has users should be prevented."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Find a role that has users (e.g. "admin" since account1 uses it)
    roles_msg = await _navigate_to_roles(account1)

    # Find the admin role — it has at least 1 user (account1)
    buttons = get_buttons(roles_msg)
    admin_btn = None
    for btn in buttons:
        if btn.data and btn.data.decode().startswith("rbac_role:"):
            # We need to find a role with users; admin is guaranteed to have one
            admin_btn = btn
            break

    assert admin_btn is not None
    role_id = int(admin_btn.data.decode().split(":")[-1])
    detail_msg = await account1.click_button(roles_msg, text=admin_btn.text)

    # UI should hide delete button for role with assigned users
    del_btn = find_button(detail_msg, f"rbac_del:{role_id}")
    assert del_btn is None, (
        f"Delete button should NOT appear for role with assigned users. "
        f"Buttons: {button_labels(detail_msg)}"
    )


async def test_delete_role_success(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Delete a role with no users — should succeed."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Create an empty role via DB
    role_id = await bot_setup.create_role("e2e_temp_role", "E2E Temp Role")
    _module_state["temp_role_id"] = role_id

    roles_msg = await _navigate_to_roles(account1)

    # Find our temp role
    role_btn = find_button(roles_msg, f"rbac_role:{role_id}")
    assert role_btn is not None, (
        f"Should find temp role button. Buttons: {button_labels(roles_msg)}"
    )
    detail_msg = await account1.click_button(roles_msg, text=role_btn.text)

    # Delete
    del_btn = find_button(detail_msg, f"rbac_del:{role_id}")
    assert del_btn is not None
    confirm_msg = await account1.click_button(detail_msg, text=del_btn.text)

    cdel_btn = find_button(confirm_msg, f"rbac_cdel:{role_id}")
    assert cdel_btn is not None
    result_msg = await account1.click_button(confirm_msg, text=cdel_btn.text)

    assert "удалена" in result_msg.text.lower(), (
        f"Expected 'удалена', got: {result_msg.text[:200]}"
    )

    # DB check
    role = await db.get_role_by_name("e2e_temp_role")
    assert role is None, "Role should be deleted from DB"
