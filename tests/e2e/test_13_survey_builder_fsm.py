import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, button_labels
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))

_module_state = {}


async def _navigate_to_survey_create(account: TelegramTestClient) -> None:
    """Navigate /menu -> Surveys -> Create and enter FSM."""
    menu_msg = await account.send_command("/menu")
    surveys_btn = find_button(menu_msg, "menu_surveys")
    assert surveys_btn is not None, (
        f"Admin menu should have surveys button. Buttons: {button_labels(menu_msg)}"
    )
    surveys_msg = await account.click_button(menu_msg, text=surveys_btn.text)

    create_btn = find_button(surveys_msg, "sb_action:create")
    assert create_btn is not None, (
        f"Survey menu should have create button. Buttons: {button_labels(surveys_msg)}"
    )
    await account.click_button(surveys_msg, text=create_btn.text)


async def _enter_survey_header(
    account: TelegramTestClient, title: str, slug: str, description: str = "-"
) -> None:
    """Fill in title, slug, description steps of the FSM."""
    await account.send_text_in_fsm(title)
    await account.send_text_in_fsm(slug)
    await account.send_text_in_fsm(description)


async def test_create_survey_text_question(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Create a survey with a single text question through the full FSM."""
    await account1.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    await _navigate_to_survey_create(account1)
    await _enter_survey_header(account1, "E2E Text Survey", "e2e_text_only")

    # Add question: enter title
    q_type_msg = await account1.send_text_in_fsm("What is your feedback?")

    # Choose type: text
    text_btn = find_button(q_type_msg, "sq_type:text")
    assert text_btn is not None, (
        f"Should find text type button. Buttons: {button_labels(q_type_msg)}"
    )
    after_q_msg = await account1.click_button(q_type_msg, text=text_btn.text)

    # Finish (don't add more questions)
    finish_btn = find_button(after_q_msg, "sb_action:finish")
    assert finish_btn is not None, (
        f"Should find finish button. Buttons: {button_labels(after_q_msg)}"
    )
    result_msg = await account1.click_button(after_q_msg, text=finish_btn.text)
    assert "создан" in result_msg.text.lower(), (
        f"Expected 'создан' in response, got: {result_msg.text[:200]}"
    )

    # DB check
    template = await db.get_survey_template_by_slug("e2e_text_only")
    assert template is not None, "Template should be created in DB"
    _module_state["text_template_id"] = template["id"]

    questions = await db.get_survey_questions(template["id"])
    assert len(questions) == 1, f"Expected 1 question, got {len(questions)}"
    assert questions[0]["question_type"] == "text"


async def test_create_survey_rating_question(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Create a survey with a rating question (min=1, max=10)."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    await _navigate_to_survey_create(account1)
    await _enter_survey_header(account1, "E2E Rating Survey", "e2e_rating_only")

    # Add question title
    q_type_msg = await account1.send_text_in_fsm("Rate your experience")

    # Choose type: rating
    rating_btn = find_button(q_type_msg, "sq_type:rating")
    assert rating_btn is not None, (
        f"Should find rating type button. Buttons: {button_labels(q_type_msg)}"
    )
    await account1.click_button(q_type_msg, text=rating_btn.text)

    # Configure rating: min=1, max=10
    await account1.send_text_in_fsm("1")
    after_q_msg = await account1.send_text_in_fsm("10")

    # Finish
    finish_btn = find_button(after_q_msg, "sb_action:finish")
    assert finish_btn is not None
    result_msg = await account1.click_button(after_q_msg, text=finish_btn.text)
    assert "создан" in result_msg.text.lower()

    # DB check
    template = await db.get_survey_template_by_slug("e2e_rating_only")
    assert template is not None
    questions = await db.get_survey_questions(template["id"])
    assert len(questions) == 1
    assert questions[0]["question_type"] == "rating"

    import json

    config = (
        json.loads(questions[0]["config"])
        if isinstance(questions[0]["config"], str)
        else questions[0]["config"]
    )
    assert config["min"] == 1
    assert config["max"] == 10


async def test_create_survey_choice_question(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Create a survey with a single_choice question with 2 options."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    await _navigate_to_survey_create(account1)
    await _enter_survey_header(account1, "E2E Choice Survey", "e2e_choice_only")

    # Add question title
    q_type_msg = await account1.send_text_in_fsm("Pick one")

    # Choose type: single_choice
    sc_btn = find_button(q_type_msg, "sq_type:single_choice")
    assert sc_btn is not None, (
        f"Should find single_choice button. Buttons: {button_labels(q_type_msg)}"
    )
    await account1.click_button(q_type_msg, text=sc_btn.text)

    # Add option 1: value -> label
    await account1.send_text_in_fsm("opt_a")
    opt_msg = await account1.send_text_in_fsm("Option A")

    # Add option 2: value -> label
    await account1.send_text_in_fsm("opt_b")
    opt_msg = await account1.send_text_in_fsm("Option B")

    # Click "options done"
    done_btn = find_button(opt_msg, "sb_action:options_done")
    assert done_btn is not None, (
        f"Should find options_done button. Buttons: {button_labels(opt_msg)}"
    )
    after_q_msg = await account1.click_button(opt_msg, text=done_btn.text)

    # Finish
    finish_btn = find_button(after_q_msg, "sb_action:finish")
    assert finish_btn is not None
    result_msg = await account1.click_button(after_q_msg, text=finish_btn.text)
    assert "создан" in result_msg.text.lower()

    # DB check
    template = await db.get_survey_template_by_slug("e2e_choice_only")
    assert template is not None
    questions = await db.get_survey_questions(template["id"])
    assert len(questions) == 1
    assert questions[0]["question_type"] == "single_choice"

    options = await db.get_survey_question_options(questions[0]["id"])
    assert len(options) == 2, f"Expected 2 options, got {len(options)}"


async def test_create_survey_multiple_questions(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Create a survey with 2 questions (text + rating)."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    await _navigate_to_survey_create(account1)
    await _enter_survey_header(account1, "E2E Multi Q Survey", "e2e_multi_q")

    # Q1: text
    q1_type_msg = await account1.send_text_in_fsm("First question")
    text_btn = find_button(q1_type_msg, "sq_type:text")
    assert text_btn is not None
    after_q1_msg = await account1.click_button(q1_type_msg, text=text_btn.text)

    # Add another question
    add_btn = find_button(after_q1_msg, "sb_action:add_question")
    assert add_btn is not None, (
        f"Should find add_question button. Buttons: {button_labels(after_q1_msg)}"
    )
    await account1.click_button(after_q1_msg, text=add_btn.text)

    # Q2: rating (min=1, max=5)
    q2_type_msg = await account1.send_text_in_fsm("Second question")
    rating_btn = find_button(q2_type_msg, "sq_type:rating")
    assert rating_btn is not None
    await account1.click_button(q2_type_msg, text=rating_btn.text)
    await account1.send_text_in_fsm("1")
    after_q2_msg = await account1.send_text_in_fsm("5")

    # Finish
    finish_btn = find_button(after_q2_msg, "sb_action:finish")
    assert finish_btn is not None
    result_msg = await account1.click_button(after_q2_msg, text=finish_btn.text)
    assert "создан" in result_msg.text.lower()

    # DB check
    template = await db.get_survey_template_by_slug("e2e_multi_q")
    assert template is not None
    questions = await db.get_survey_questions(template["id"])
    assert len(questions) == 2, f"Expected 2 questions, got {len(questions)}"


async def test_create_survey_cancel(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Cancel survey creation mid-FSM — template should NOT be created."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    await _navigate_to_survey_create(account1)

    # Enter title
    slug_msg = await account1.send_text_in_fsm("E2E Cancel Survey")

    # Cancel instead of entering slug
    cancel_btn = find_button(slug_msg, "sb_action:cancel")
    if cancel_btn:
        await account1.click_button(slug_msg, text=cancel_btn.text)
    else:
        # FSM cancel via /start
        await account1.send_command_multi("/start", count=2)

    # DB check: template should NOT exist
    template = await db.get_survey_template_by_slug("e2e_cancel_survey")
    assert template is None, "Cancelled survey should not be created in DB"
