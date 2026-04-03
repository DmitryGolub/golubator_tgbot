import os

from tests.e2e.helpers.buttons import find_button, get_buttons, button_labels
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))


async def test_help_command(
    account1: TelegramTestClient,
    setup: E2ESetup,
):
    """/help shows menu with inline buttons."""
    await setup.ensure_user_record(ACCOUNT_1_TG_ID)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    help_msg = await account1.send_command("/help")
    assert help_msg.text is not None

    buttons = get_buttons(help_msg)
    assert len(buttons) > 0, (
        f"/help should show inline buttons, got: {help_msg.text[:200]}"
    )


async def test_job_search_report(
    account1: TelegramTestClient,
    setup: E2ESetup,
):
    """Open job search report menu and select a period."""
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_role_permission("admin", "view_job_search_reports")

    # Navigate via press_callback (may not be in main menu for all roles)
    period_msg = await account1.press_callback("job_search_report_menu")
    assert period_msg.text is not None

    # Choose "all time" period
    period_btn = find_button(period_msg, "job_search_period:all")
    if period_btn is None:
        period_btn = find_button(period_msg, "job_search_period:")
    assert period_btn is not None, (
        f"Should find period button. Buttons: {button_labels(period_msg)}"
    )
    result_msg = await account1.click_button(period_msg, text=period_btn.text)
    assert result_msg.text is not None, "Report should return text"


async def test_education_feedback(
    account1: TelegramTestClient,
    setup: E2ESetup,
):
    """Open education feedback report and select a period."""
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_role_permission("admin", "view_education_feedback")

    period_msg = await account1.press_callback("education_feedback_menu")
    assert period_msg.text is not None

    period_btn = find_button(period_msg, "education_period:all")
    if period_btn is None:
        period_btn = find_button(period_msg, "education_period:")
    assert period_btn is not None, (
        f"Should find period button. Buttons: {button_labels(period_msg)}"
    )
    result_msg = await account1.click_button(period_msg, text=period_btn.text)
    assert result_msg.text is not None, "Report should return text"


async def test_direction_students(
    account1: TelegramTestClient,
    setup: E2ESetup,
):
    """Lead views students by direction."""
    await setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_role_permission("admin", "view_direction_students")

    result_msg = await account1.press_callback("lead_direction_students")
    assert result_msg.text is not None
    # Either shows directions or "no directions" message
    text = result_msg.text.lower()
    assert len(text) > 0, "Should have response text"
