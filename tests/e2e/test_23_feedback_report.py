import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))
ACCOUNT_3_TG_ID = int(os.environ.get("TEST_ACCOUNT_3_TG_ID", "0"))


async def test_problem_report_to_admin(
    account2: TelegramTestClient,
    account3: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """account2 sends a problem report to coordinator → account3 (admin) receives it."""
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")

    await account3.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_3_TG_ID, "admin")

    # Snapshot account3's inbox before sending
    marker = await account3.snapshot_last_message_id()

    # account2 opens feedback menu
    msg = await account2.press_callback("feedback_report_menu")

    # Choose "problem" type
    msg = await account2.click_button(msg, data="fb_type:problem")

    # Enter problem text — bot sends new message with recipient buttons
    msg = await account2.send_text_in_fsm("E2E problem report test message")

    # Choose "admin" (Координатор) as recipient
    msg = await account2.click_button(msg, data="fb_rcpt:admin")
    assert msg.text is not None, "Expected confirmation message after sending"

    # Verify account3 received the notification
    notification = await account3.wait_for_message_after(marker, timeout=20)
    assert "E2E problem report test message" in notification.text, (
        f"Expected report text in admin notification, got: {notification.text[:300]}"
    )
    assert (
        "Обращение" in notification.text or "обращение" in notification.text.lower()
    ), f"Expected 'Обращение' prefix in notification, got: {notification.text[:300]}"


async def test_bug_report_without_photo(
    account2: TelegramTestClient,
    account3: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """account2 sends a bug report without photo → admin (account3) receives plain text."""
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")

    await account3.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_3_TG_ID, "admin")

    marker = await account3.snapshot_last_message_id()

    # Open feedback menu and choose bug type
    msg = await account2.press_callback("feedback_report_menu")
    msg = await account2.click_button(msg, data="fb_type:bug")

    # Enter bug description — bot sends new message with skip-photo button
    msg = await account2.send_text_in_fsm("E2E bug report without photo")

    # Skip photo — bot edits message with confirmation and sends to admins
    msg = await account2.click_button(msg, data="fb_skip")
    assert msg.text is not None, "Expected confirmation message after bug report"

    # Verify account3 received the bug report
    notification = await account3.wait_for_message_after(marker, timeout=20)
    assert "E2E bug report without photo" in notification.text, (
        f"Expected bug text in admin notification, got: {notification.text[:300]}"
    )
    assert "Баг" in notification.text or "баг" in notification.text.lower(), (
        f"Expected 'Баг' prefix in notification, got: {notification.text[:300]}"
    )
