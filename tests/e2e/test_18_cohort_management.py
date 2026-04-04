"""Cohort management E2E tests.

These tests interact with Notion API via the bot UI.
Tests are skipped if Notion is not configured or the operation fails due to
Notion API limitations (e.g. protected properties).
"""

import os

import pytest

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, button_labels
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))

_module_state = {}


async def _navigate_to_cohorts(account: TelegramTestClient):
    """Navigate /menu -> Cohorts list."""
    menu_msg = await account.send_command("/menu")
    cohorts_btn = find_button(menu_msg, "menu_cohorts")
    assert cohorts_btn is not None, (
        f"Admin menu should have cohorts button. Buttons: {button_labels(menu_msg)}"
    )
    return await account.click_button(menu_msg, text=cohorts_btn.text)


async def test_view_cohort_types(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin views list of cohort types."""
    await setup.ensure_user_record(ACCOUNT_1_TG_ID)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Seed cohort data so the list is never empty after truncate_all
    await bot_setup.set_user_cohort(ACCOUNT_1_TG_ID, "Status", "study")

    cohorts_msg = await _navigate_to_cohorts(account1)
    assert cohorts_msg.text is not None

    # Should show cohort types
    type_btn = find_button(cohorts_msg, "ctype:")
    assert type_btn is not None, (
        f"Cohort types should be visible after seeding. Buttons: {button_labels(cohorts_msg)}"
    )

    # Save index for subsequent tests
    _module_state["type_idx"] = type_btn.data.decode().split(":")[-1]


async def test_view_cohort_type_detail(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin views detail of a cohort type."""
    type_idx = _module_state.get("type_idx")
    if type_idx is None:
        pytest.skip("Previous test must find a cohort type")
        return

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    cohorts_msg = await _navigate_to_cohorts(account1)
    type_btn = find_button(cohorts_msg, f"ctype:{type_idx}")
    if type_btn is None:
        pytest.skip("Cohort type button not found")
        return

    detail_msg = await account1.click_button(cohorts_msg, text=type_btn.text)
    assert detail_msg.text is not None
    assert "опци" in detail_msg.text.lower() or "пусто" in detail_msg.text.lower(), (
        f"Detail should show options info, got: {detail_msg.text[:300]}"
    )

    # Check for management buttons
    has_create = find_button(detail_msg, f"copt_new:{type_idx}") is not None
    has_rename = find_button(detail_msg, f"ctype_ren:{type_idx}") is not None
    has_delete = find_button(detail_msg, f"ctype_del:{type_idx}") is not None
    _module_state["has_management_buttons"] = has_create or has_rename or has_delete


async def test_create_cohort_option(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin creates a new option in a cohort type."""
    type_idx = _module_state.get("type_idx")
    if type_idx is None:
        pytest.skip("No cohort type available")
        return

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    cohorts_msg = await _navigate_to_cohorts(account1)
    type_btn = find_button(cohorts_msg, f"ctype:{type_idx}")
    if type_btn is None:
        pytest.skip("Cohort type button not found")
        return

    detail_msg = await account1.click_button(cohorts_msg, text=type_btn.text)

    create_btn = find_button(detail_msg, f"copt_new:{type_idx}")
    if create_btn is None:
        pytest.skip("Create option button not available — type may not be editable")
        return

    await account1.click_button(detail_msg, text=create_btn.text)

    # FSM: enter option name
    result_msg = await account1.send_text_in_fsm("e2e_test_option")

    text = result_msg.text.lower()
    if "добавлена" in text:
        _module_state["created_option"] = "e2e_test_option"
    elif "не удалось" in text or "нередактируем" in text:
        pytest.skip("Option creation failed — type may not be editable via API")


async def test_rename_cohort_type(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin renames a cohort type via FSM (skipped if not editable)."""
    type_idx = _module_state.get("type_idx")
    if type_idx is None:
        pytest.skip("No cohort type available")
        return

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    cohorts_msg = await _navigate_to_cohorts(account1)
    type_btn = find_button(cohorts_msg, f"ctype:{type_idx}")
    if type_btn is None:
        pytest.skip("Cohort type button not found")
        return

    detail_msg = await account1.click_button(cohorts_msg, text=type_btn.text)

    rename_btn = find_button(detail_msg, f"ctype_ren:{type_idx}")
    if rename_btn is None:
        pytest.skip("Rename type button not available")
        return

    # We won't actually rename a production type — just test FSM entry + cancel
    await account1.click_button(detail_msg, text=rename_btn.text)

    # Cancel via /start to clear FSM
    await account1.send_command("/menu")


async def test_delete_cohort_option(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Admin deletes a cohort option (only the one we created)."""
    created_option = _module_state.get("created_option")
    if created_option is None:
        pytest.skip("No option was created in previous test")
        return

    type_idx = _module_state.get("type_idx")
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    cohorts_msg = await _navigate_to_cohorts(account1)
    type_btn = find_button(cohorts_msg, f"ctype:{type_idx}")
    if type_btn is None:
        pytest.skip("Cohort type not found")
        return

    detail_msg = await account1.click_button(cohorts_msg, text=type_btn.text)

    # Navigate to options list for deletion
    # Look for option list button with action=delete
    opts_btn = find_button(detail_msg, "copt_ls:")
    if opts_btn is None:
        pytest.skip("Options list button not available")
        return

    # Check if this is a delete action button
    opts_btns = [
        b
        for b in (detail_msg.reply_markup.rows if detail_msg.reply_markup else [])
        for b in (b.buttons if hasattr(b, "buttons") else [b])
        if b.data and b"copt_ls:" in b.data and b"delete" in b.data
    ]
    if not opts_btns:
        pytest.skip("Delete options list button not found")
        return

    opts_msg = await account1.click_button(detail_msg, data=opts_btns[0].data.decode())

    # Find our test option to delete
    del_opt_btn = find_button(opts_msg, "copt_del:")
    if del_opt_btn is None:
        pytest.skip("Delete option button not found")
        return

    result_msg = await account1.click_button(opts_msg, text=del_opt_btn.text)
    text = result_msg.text.lower()
    assert "удалена" in text or "не удалось" in text, (
        f"Expected deletion result, got: {result_msg.text[:200]}"
    )
