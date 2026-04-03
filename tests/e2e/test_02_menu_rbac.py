import os

from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

# Minimum number of buttons expected for admin menu
ADMIN_MIN_BUTTONS = 5


def _extract_buttons(msg) -> list[dict]:
    """Extract inline buttons from a Telethon Message as list of {text, data}."""
    buttons = []
    if msg.reply_markup and hasattr(msg.reply_markup, "rows"):
        for row in msg.reply_markup.rows:
            for btn in row.buttons:
                data = btn.data.decode() if isinstance(btn.data, bytes) else btn.data
                buttons.append({"text": btn.text, "data": data})
    return buttons


async def test_admin_full_menu(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
):
    """
    Admin user should see a full menu with all admin buttons (>= 5).
    """
    # Register account1 and assign admin role
    await account1.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Request menu — bot may send text + keyboard as one message,
    # or access_denied if permissions not yet cached
    msg = await account1.send_command("/menu", timeout=15)

    # If bot returned access_denied, try /start again to refresh permissions
    if msg.reply_markup is None:
        await account1.send_command_multi("/start", count=2)
        msg = await account1.send_command("/menu", timeout=15)

    assert msg.reply_markup is not None, (
        f"Admin menu should have inline keyboard, got text: {msg.text[:200] if msg.text else 'None'}"
    )

    buttons = _extract_buttons(msg)
    button_count = len(buttons)

    assert button_count >= ADMIN_MIN_BUTTONS, (
        f"Admin should see at least {ADMIN_MIN_BUTTONS} buttons, got {button_count}: "
        f"{[b['text'] for b in buttons]}"
    )

    # Verify key admin callback_data values are present
    callback_data_values = {b["data"] for b in buttons}
    expected_admin_callbacks = {"menu_users", "menu_cohorts", "menu_roles"}
    missing = expected_admin_callbacks - callback_data_values
    assert not missing, (
        f"Admin menu is missing expected callbacks: {missing}. "
        f"Available: {callback_data_values}"
    )


async def test_student_limited_menu(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
):
    """
    Student (default role) should see fewer menu buttons than admin.
    """
    # Register account2 (student by default)
    await account2.send_command_multi("/start", count=2)

    # Request menu
    msg = await account2.send_command("/menu", timeout=15)

    assert msg.reply_markup is not None, "Student menu should have inline keyboard"

    student_buttons = _extract_buttons(msg)
    student_count = len(student_buttons)

    # Student should have strictly fewer buttons than admin minimum
    assert student_count < ADMIN_MIN_BUTTONS, (
        f"Student should see fewer than {ADMIN_MIN_BUTTONS} buttons, "
        f"got {student_count}: {[b['text'] for b in student_buttons]}"
    )


async def test_student_cannot_access_admin(
    account2: TelegramTestClient,
    db: DBAssertions,
):
    """
    Student menu should NOT contain admin-only callback_data entries.
    Verifies RBAC by checking button absence rather than trying to invoke them.
    """
    # Request menu as student (account2, registered in previous test)
    msg = await account2.send_command("/menu", timeout=15)

    assert msg.reply_markup is not None, "Student menu should have inline keyboard"

    buttons = _extract_buttons(msg)
    callback_data_values = {b["data"] for b in buttons}

    admin_only_callbacks = {"menu_roles", "menu_users", "menu_cohorts", "menu_triggers"}
    leaked = admin_only_callbacks & callback_data_values

    assert not leaked, (
        f"Student menu should NOT contain admin callbacks, but found: {leaked}"
    )
