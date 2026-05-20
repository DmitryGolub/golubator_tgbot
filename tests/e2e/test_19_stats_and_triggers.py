import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state = {}


async def test_admin_view_mentor_detail_stats(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin selects a mentor and views their detailed stats."""
    await account1.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)

    # Navigate via press_callback to admin_mentor_stats
    select_msg = await account1.press_callback("admin_mentor_stats")

    # Find a mentor button
    mentor_btn = find_button(select_msg, "mstats:")
    assert mentor_btn is not None, (
        f"Should find mentor stats button. Buttons: {button_labels(select_msg)}"
    )

    detail_msg = await account1.click_button(select_msg, text=mentor_btn.text)

    text = detail_msg.text.lower()
    assert "созвоны" in text, (
        f"Expected 'Созвоны' in mentor stats, got: {detail_msg.text[:300]}"
    )
    assert "опрос" in text, (
        f"Expected 'Опрос' in mentor stats, got: {detail_msg.text[:300]}"
    )


async def test_view_trigger_rule_detail(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Admin views trigger rule detail."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Create a trigger rule so we have something to view
    rule_id = await bot_setup.create_trigger_rule(
        name="E2E Detail Test Rule",
        trigger_type="manual",
        action_type="send_notification",
        recipient_type="specific_users",
        action_config={"text": "Test notification"},
        recipient_config={"user_ids": [ACCOUNT_1_TG_ID]},
    )
    _module_state["rule_id"] = rule_id

    # Navigate: /menu -> Triggers -> List -> Detail
    menu_msg = await account1.send_command("/menu")
    triggers_btn = find_button(menu_msg, "menu_triggers")
    assert triggers_btn is not None, (
        f"Admin menu should have triggers button. Buttons: {button_labels(menu_msg)}"
    )
    triggers_msg = await account1.click_button(menu_msg, text=triggers_btn.text)

    list_btn = find_button(triggers_msg, "tr_action:list")
    assert list_btn is not None, (
        f"Triggers menu should have list button. Buttons: {button_labels(triggers_msg)}"
    )
    list_msg = await account1.click_button(triggers_msg, text=list_btn.text)

    # Find our rule
    detail_btn = find_button(list_msg, f"tr_detail:{rule_id}")
    assert detail_btn is not None, (
        f"Should find trigger detail button for rule {rule_id}. "
        f"Buttons: {button_labels(list_msg)}"
    )
    detail_msg = await account1.click_button(list_msg, text=detail_btn.text)

    text = detail_msg.text.lower()
    assert "e2e detail test rule" in text, (
        f"Expected rule name in detail, got: {detail_msg.text[:300]}"
    )
    assert "триггер" in text or "действие" in text, (
        f"Expected trigger info in detail, got: {detail_msg.text[:300]}"
    )
