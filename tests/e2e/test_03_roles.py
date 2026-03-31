import os

from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import TestSetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state = {}


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
            for btn in row.buttons:
                buttons.append(btn)
    return buttons


async def test_create_role_via_bot(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Create a role through bot FSM and verify in DB."""
    # Setup: register and make admin
    await account1.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    # Navigate: /menu -> Roles (retry after /start if permissions not cached)
    menu_msg = await account1.send_command("/menu")
    if menu_msg.reply_markup is None:
        await account1.send_command_multi("/start", count=2)
        menu_msg = await account1.send_command("/menu")
    roles_btn = _find_button(menu_msg, "menu_roles")
    assert roles_btn is not None, (
        f"Admin menu should have 'Roles' button, got: {menu_msg.text[:200] if menu_msg.text else 'None'}"
    )

    roles_msg = await account1.click_button(menu_msg, text=roles_btn.text)

    # Clean up any leftover e2e role from previous runs
    await db._pool.execute(
        "DELETE FROM iam.role_permissions WHERE role_id IN (SELECT id FROM iam.roles WHERE name = 'e2e_test_role')"
    )
    await db._pool.execute("DELETE FROM iam.roles WHERE name = 'e2e_test_role'")

    # Click "Create role"
    create_btn = _find_button(roles_msg, "rbac_create_role")
    assert create_btn is not None, "Roles list should have 'Create role' button"
    await account1.click_button(roles_msg, text=create_btn.text)

    # FSM: enter system name
    resp1 = await account1.send_text_in_fsm("e2e_test_role")
    assert resp1.text is not None

    # FSM: enter display name
    resp2 = await account1.send_text_in_fsm("E2E Тестовая роль")
    assert "E2E Тестовая роль" in resp2.text or "создана" in resp2.text.lower()

    # DB check
    roles = await db.get_roles()
    role = next((r for r in roles if r["name"] == "e2e_test_role"), None)
    assert role is not None, "Role e2e_test_role should exist in DB"
    _module_state["role"] = role


async def test_assign_permissions_to_role(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """Assign view_own_info permission to the created role."""
    role = _module_state.get("role")
    assert role is not None, "Previous test must create a role"
    role_id = role["id"]

    # Navigate to roles list
    menu_msg = await account1.send_command("/menu")
    roles_btn = _find_button(menu_msg, "menu_roles")
    roles_msg = await account1.click_button(menu_msg, text=roles_btn.text)

    # Find and click role detail button
    detail_btn = _find_button(roles_msg, f"rbac_role:{role_id}")
    assert detail_btn is not None, f"Should find role detail button for id={role_id}"
    detail_msg = await account1.click_button(roles_msg, text=detail_btn.text)

    # Click "Permissions"
    perms_btn = _find_button(detail_msg, "rbac_edit_perms:")
    assert perms_btn is not None, "Role detail should have 'Permissions' button"
    perms_msg = await account1.click_button(detail_msg, text=perms_btn.text)

    # Find view_own_info toggle button and click it
    buttons = _get_buttons(perms_msg)
    view_btn = None
    for btn in buttons:
        if (
            btn.data
            and b"rbac_perm:" in btn.data
            and "view_own_info" in btn.text.lower()
        ):
            view_btn = btn
            break

    # If not found by text, find any toggle_perm button that relates to view_own_info
    if view_btn is None:
        # The permission buttons show codename in text; look for it
        for btn in buttons:
            if btn.data and b"rbac_perm:" in btn.data:
                if "view_own" in btn.text:
                    view_btn = btn
                    break

    assert view_btn is not None, (
        f"Should find view_own_info toggle button. Available: "
        f"{[(b.text, b.data.decode() if b.data else '') for b in buttons]}"
    )
    await account1.click_button(perms_msg, text=view_btn.text)

    # DB check: role should have view_own_info permission
    perms = await db.get_role_permissions(role_id)
    perm_names = [p["codename"] for p in perms]
    assert "view_own_info" in perm_names, (
        f"Role should have view_own_info, got: {perm_names}"
    )


async def test_assign_role_to_user(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Assign the created role to account2 via setup helper."""
    # Ensure account2 is registered
    await account2.send_command_multi("/start", count=2)

    # Assign role via direct DB (FSM navigation is too complex for this test)
    await setup.set_user_role(ACCOUNT_2_TG_ID, "e2e_test_role")

    # DB check
    await db.assert_user_has_role(ACCOUNT_2_TG_ID, "e2e_test_role")


async def test_menu_updates_after_role_change(
    account2: TelegramTestClient,
):
    """After role change, menu should reflect new permissions."""
    # account2 now has e2e_test_role with view_own_info permission
    msg = await account2.send_command("/menu")

    assert msg.reply_markup is not None, "Menu should have inline keyboard"

    buttons = _get_buttons(msg)
    callback_data = [
        btn.data.decode() if isinstance(btn.data, bytes) else btn.data
        for btn in buttons
        if btn.data
    ]

    # view_own_info without view_students -> student_me_info button
    assert "student_me_info" in callback_data, (
        f"Menu should contain student_me_info for view_own_info. Got: {callback_data}"
    )

    # Should NOT have admin buttons
    assert "menu_roles" not in callback_data
    assert "menu_users" not in callback_data
