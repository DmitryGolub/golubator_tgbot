"""Cohort option rename E2E tests.

Covers the full rename flow and navigation that previously triggered
'message is not modified' errors before the safe_edit_text fix.
"""

import os

import pytest

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons, button_labels
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


async def _navigate_to_detail(account: TelegramTestClient, type_idx: str):
    """Navigate to cohort type detail by index."""
    cohorts_msg = await _navigate_to_cohorts(account)
    type_btn = find_button(cohorts_msg, f"ctype:{type_idx}")
    if type_btn is None:
        pytest.skip(f"Cohort type button ctype:{type_idx} not found")
    detail_msg = await account.click_button(cohorts_msg, text=type_btn.text)
    return detail_msg


async def test_setup_cohort_for_rename(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Setup: seed cohort data and create a test option for rename tests."""
    await account1.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await bot_setup.set_user_cohort(ACCOUNT_1_TG_ID, "Status", "study")
    await bot_setup.set_user_cohort(ACCOUNT_1_TG_ID, "Category", "e2e_rename_opt")

    cohorts_msg = await _navigate_to_cohorts(account1)

    # Pick an editable type (not Status/Mentor)
    type_btn = None
    for btn in get_buttons(cohorts_msg):
        if btn.data and btn.data.decode().startswith("ctype:"):
            if btn.text not in ("Status", "Mentor", "Ментор"):
                type_btn = btn
                break
    if type_btn is None:
        type_btn = find_button(cohorts_msg, "ctype:")
    if type_btn is None:
        pytest.skip("No cohort types found")

    type_idx = type_btn.data.decode().split(":")[-1]
    _module_state["type_idx"] = type_idx

    detail_msg = await account1.click_button(cohorts_msg, text=type_btn.text)

    # Create a test option for rename
    create_btn = find_button(detail_msg, f"copt_new:{type_idx}")
    if create_btn is None:
        pytest.skip("Create option button not available — type not editable")

    await account1.click_button(detail_msg, text=create_btn.text)
    result_msg = await account1.send_text_in_fsm("e2e_rename_src")

    text = result_msg.text.lower()
    if "добавлена" in text:
        _module_state["created_option"] = "e2e_rename_src"
    else:
        pytest.skip(f"Option creation failed: {result_msg.text[:200]}")


async def test_rename_option_full_flow(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Full rename flow: navigate to option, enter new name, verify."""
    type_idx = _module_state.get("type_idx")
    created = _module_state.get("created_option")
    if not type_idx or not created:
        pytest.skip("Setup test must succeed first")

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    detail_msg = await _navigate_to_detail(account1, type_idx)

    # Find rename options list button
    rename_list_btn = None
    for btn in get_buttons(detail_msg):
        if btn.data:
            data = btn.data.decode()
            if data.startswith("copt_ls:") and "rename" in data:
                rename_list_btn = btn
                break
    if rename_list_btn is None:
        pytest.skip("Rename options list button not available")

    # Navigate to options list for rename
    opts_msg = await account1.click_button(
        detail_msg, data=rename_list_btn.data.decode()
    )

    # Find our test option in the rename list
    rename_btn = None
    for btn in get_buttons(opts_msg):
        if btn.data and btn.data.decode().startswith("copt_ren:"):
            if btn.text == created:
                rename_btn = btn
                break
    # Fallback: pick first rename option button
    if rename_btn is None:
        rename_btn = find_button(opts_msg, "copt_ren:")
    if rename_btn is None:
        pytest.skip(
            f"Rename option button not found. Buttons: {button_labels(opts_msg)}"
        )

    _module_state["rename_btn_text"] = rename_btn.text

    # Click to start rename FSM
    await account1.click_button(opts_msg, text=rename_btn.text)

    # FSM: enter new name
    new_name = "e2e_rename_dst"
    result_msg = await account1.send_text_in_fsm(new_name)

    text = result_msg.text.lower()
    assert "переименована" in text or "успешно" in text or new_name.lower() in text, (
        f"Expected rename confirmation, got: {result_msg.text[:300]}"
    )
    _module_state["new_option_name"] = new_name


async def test_rename_option_back_to_detail_after_rename(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """After rename, navigate back to detail — verifies safe_edit_text handles 'not modified'."""
    type_idx = _module_state.get("type_idx")
    new_name = _module_state.get("new_option_name")
    if not type_idx or not new_name:
        pytest.skip("Rename test must succeed first")

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Navigate back to detail — this is where 'message is not modified' used to crash
    detail_msg = await _navigate_to_detail(account1, type_idx)
    assert detail_msg.text is not None, "Detail page should open without error"

    # Verify new option name appears in detail
    assert new_name in detail_msg.text, (
        f"New option name '{new_name}' should appear in detail. Got: {detail_msg.text[:300]}"
    )


async def test_rename_option_cancel(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Cancel rename via FSM cancel button — bot should remain responsive."""
    type_idx = _module_state.get("type_idx")
    if not type_idx:
        pytest.skip("Setup test must succeed first")

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    detail_msg = await _navigate_to_detail(account1, type_idx)

    # Find rename options list button
    rename_list_btn = None
    for btn in get_buttons(detail_msg):
        if btn.data:
            data = btn.data.decode()
            if data.startswith("copt_ls:") and "rename" in data:
                rename_list_btn = btn
                break
    if rename_list_btn is None:
        pytest.skip("Rename options list button not available")

    opts_msg = await account1.click_button(
        detail_msg, data=rename_list_btn.data.decode()
    )

    rename_btn = find_button(opts_msg, "copt_ren:")
    if rename_btn is None:
        pytest.skip("No option to rename")

    # Start rename FSM
    fsm_msg = await account1.click_button(opts_msg, text=rename_btn.text)

    # Cancel FSM
    cancel_btn = find_button(fsm_msg, "cohort_cancel_fsm")
    if cancel_btn is not None:
        await account1.click_button(fsm_msg, text=cancel_btn.text)
    else:
        # Fallback: clear FSM via /menu
        await account1.send_command("/menu")

    # Verify bot is responsive after cancel
    menu_msg = await account1.send_command("/menu")
    assert menu_msg.text is not None, "Bot should be responsive after cancel"
    assert find_button(menu_msg, "menu_cohorts") is not None


async def test_cohort_detail_roundtrip(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Quick navigation detail <-> list — safe_edit_text handles repeated transitions."""
    type_idx = _module_state.get("type_idx")
    if not type_idx:
        pytest.skip("Setup test must succeed first")

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # Round 1: list -> detail
    cohorts_msg = await _navigate_to_cohorts(account1)
    type_btn = find_button(cohorts_msg, f"ctype:{type_idx}")
    if type_btn is None:
        pytest.skip("Cohort type not found")

    detail_msg = await account1.click_button(cohorts_msg, text=type_btn.text)
    assert detail_msg.text is not None

    # Round 1: detail -> list
    back_btn = find_button(detail_msg, "cohort_list")
    if back_btn is None:
        pytest.skip("Back to list button not found")
    list_msg = await account1.click_button(detail_msg, text=back_btn.text)
    assert find_button(list_msg, "ctype:") is not None

    # Round 2: list -> detail -> list
    type_btn2 = find_button(list_msg, f"ctype:{type_idx}")
    detail_msg2 = await account1.click_button(list_msg, text=type_btn2.text)
    assert detail_msg2.text is not None

    back_btn2 = find_button(detail_msg2, "cohort_list")
    list_msg2 = await account1.click_button(detail_msg2, text=back_btn2.text)
    assert find_button(list_msg2, "ctype:") is not None, (
        "Bot should handle repeated detail<->list transitions"
    )


async def test_cleanup_rename_option(
    account1: TelegramTestClient,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Cleanup: delete the renamed test option."""
    type_idx = _module_state.get("type_idx")
    new_name = _module_state.get("new_option_name")
    if not type_idx or not new_name:
        pytest.skip("Nothing to clean up")

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    detail_msg = await _navigate_to_detail(account1, type_idx)

    # Find delete options list button
    delete_list_btn = None
    for btn in get_buttons(detail_msg):
        if btn.data:
            data = btn.data.decode()
            if data.startswith("copt_ls:") and "delete" in data:
                delete_list_btn = btn
                break
    if delete_list_btn is None:
        return  # no cleanup needed

    opts_msg = await account1.click_button(
        detail_msg, data=delete_list_btn.data.decode()
    )

    # Find our renamed option
    del_btn = None
    for btn in get_buttons(opts_msg):
        if btn.data and btn.data.decode().startswith("copt_del:"):
            if btn.text == new_name:
                del_btn = btn
                break

    if del_btn is not None:
        await account1.click_button(opts_msg, text=del_btn.text)
