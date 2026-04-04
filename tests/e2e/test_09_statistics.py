import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))


async def test_mentor_stats_display(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Mentor can view own stats via menu."""
    await account1.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)

    menu_msg = await account1.send_command("/menu")
    info_btn = find_button(menu_msg, "mentor_me_info")
    assert info_btn is not None, (
        "Mentor menu should have 'My info' button (mentor_me_info)"
    )

    stats_msg = await account1.click_button(menu_msg, text=info_btn.text)
    assert stats_msg.text is not None
    assert "Созвоны" in stats_msg.text, (
        f"Stats should contain 'Созвоны', got: {stats_msg.text[:200]}"
    )


async def test_admin_mentor_stats(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin can view mentor stats selection list."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)

    menu_msg = await account1.send_command("/menu")
    admin_stats_btn = find_button(menu_msg, "admin_mentor_stats")
    assert admin_stats_btn is not None, (
        "Admin menu should have 'Mentor stats' button (admin_mentor_stats)"
    )

    stats_msg = await account1.click_button(menu_msg, text=admin_stats_btn.text)
    assert stats_msg.reply_markup is not None, (
        "Admin mentor stats should show mentor selection keyboard"
    )
    # Should have at least one mentor button
    buttons = []
    if hasattr(stats_msg.reply_markup, "rows"):
        for row in stats_msg.reply_markup.rows:
            buttons.extend(row.buttons)
    assert len(buttons) >= 1, "Should show at least one mentor to select"
