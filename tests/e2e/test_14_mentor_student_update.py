import os

from tests.e2e.helpers.buttons import find_button, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))


async def test_mentor_update_student_status(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
):
    """Mentor updates their student's status cohort via bot."""
    # Setup: account1 = mentor with update_student_status,
    #        account2 = mentee with Status cohort
    await setup.ensure_user_record(ACCOUNT_1_TG_ID)
    await setup.ensure_user_record(ACCOUNT_2_TG_ID)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_role_permission("mentor", "update_student_status")
    await setup.ensure_role_permission("mentor", "view_students")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)
    await setup.ensure_user_cohort(ACCOUNT_2_TG_ID, "Status", "study")

    # /menu -> "Мои ученики" -> "Обновить статус"
    menu_msg = await account1.send_command("/menu")
    students_btn = find_button(menu_msg, "mentor_students_menu")
    assert students_btn is not None, (
        f"Mentor menu should have students button. Buttons: {button_labels(menu_msg)}"
    )
    students_msg = await account1.click_button(menu_msg, text=students_btn.text)

    update_btn = find_button(students_msg, "mentor_update_student")
    assert update_btn is not None, (
        f"Students menu should have update button. Buttons: {button_labels(students_msg)}"
    )
    status_msg = await account1.click_button(
        students_msg, text=update_btn.text, timeout=30
    )

    # Choose a status value (any available)
    status_btn = find_button(status_msg, "upd_enum:status:")
    assert status_btn is not None, (
        f"Should find status value button. Buttons: {button_labels(status_msg)}"
    )
    chosen_status = status_btn.data.decode().split(":")[-1]
    mentee_msg = await account1.click_button(status_msg, text=status_btn.text)

    # Choose mentee (account2)
    mentee_btn = find_button(mentee_msg, "upd_mentee:")
    assert mentee_btn is not None, (
        f"Should find mentee button. Buttons: {button_labels(mentee_msg)}"
    )
    result_msg = await account1.click_button(mentee_msg, text=mentee_btn.text)
    assert (
        "обновлено" in result_msg.text.lower() or "статус" in result_msg.text.lower()
    ), f"Expected confirmation text, got: {result_msg.text[:200]}"

    # DB check: cohort should be updated
    cohorts = await db.get_user_cohorts(ACCOUNT_2_TG_ID)
    status_cohorts = [c for c in cohorts if c["type"] == "Status"]
    assert len(status_cohorts) > 0, "User should have Status cohort"
    assert status_cohorts[0]["value"] == chosen_status, (
        f"Expected status '{chosen_status}', got '{status_cohorts[0]['value']}'"
    )
