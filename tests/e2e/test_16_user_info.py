import os

from tests.e2e.helpers.buttons import find_button, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import TestSetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))


async def test_mentor_me_info(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Mentor views their own info via mentor_me_info."""
    await account1.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_role_permission("mentor", "view_own_info")

    menu_msg = await account1.send_command("/menu")
    me_btn = find_button(menu_msg, "mentor_me_info")
    assert me_btn is not None, (
        f"Mentor menu should have me_info button. Buttons: {button_labels(menu_msg)}"
    )
    info_msg = await account1.click_button(menu_msg, text=me_btn.text)

    text = info_msg.text.lower()
    assert "созвоны" in text, f"Expected 'Созвоны' in info, got: {info_msg.text[:300]}"


async def test_student_me_info(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Student views their own info via student_me_info."""
    await account2.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await setup.ensure_role_permission("student", "view_own_info")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    menu_msg = await account2.send_command("/menu")
    me_btn = find_button(menu_msg, "student_me_info")
    assert me_btn is not None, (
        f"Student menu should have me_info button. Buttons: {button_labels(menu_msg)}"
    )
    info_msg = await account2.click_button(menu_msg, text=me_btn.text)

    text = info_msg.text.lower()
    assert "роль" in text or "ментор" in text, (
        f"Expected 'Роль' or 'Ментор' in info, got: {info_msg.text[:300]}"
    )


async def test_mentor_students_menu(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Mentor views their students list."""
    await setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_role_permission("mentor", "view_students")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    menu_msg = await account1.send_command("/menu")
    students_btn = find_button(menu_msg, "mentor_students_menu")
    assert students_btn is not None, (
        f"Mentor menu should have students button. Buttons: {button_labels(menu_msg)}"
    )
    students_msg = await account1.click_button(menu_msg, text=students_btn.text)

    # Should contain student info or "no students" message
    assert students_msg.text is not None
    text = students_msg.text.lower()
    assert "направлен" in text or "состояние" in text or "нет" in text, (
        f"Expected students info, got: {students_msg.text[:300]}"
    )


async def test_my_surveys_menu(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
):
    """Student views 'My surveys' menu via press_callback."""
    await setup.set_user_role(ACCOUNT_2_TG_ID, "student")

    surveys_msg = await account2.press_callback("my_surveys")

    assert surveys_msg.text is not None
    text = surveys_msg.text.lower()
    assert "опрос" in text or "нет" in text, (
        f"Expected surveys-related text, got: {surveys_msg.text[:300]}"
    )
