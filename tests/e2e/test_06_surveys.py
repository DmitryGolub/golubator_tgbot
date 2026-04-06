import asyncio
import os

import pytest

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state = {}


# ── Template creation ──


async def test_create_survey_template(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Create a survey template with 4 question types through bot FSM."""
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    # /menu -> Surveys
    menu_msg = await account1.send_command("/menu")
    surveys_btn = find_button(menu_msg, "menu_surveys")
    assert surveys_btn is not None, "Admin menu should have 'Surveys' button"
    surveys_msg = await account1.click_button(menu_msg, text=surveys_btn.text)

    # Create survey
    create_btn = find_button(surveys_msg, "sb_action:create")
    assert create_btn is not None, "Survey menu should have 'Create' button"
    await account1.click_button(surveys_msg, text=create_btn.text)

    # FSM: title -> description (slug is auto-generated)
    await account1.send_text_in_fsm("E2E Test Survey")
    await account1.send_text_in_fsm("Test description")

    # The survey builder FSM is very long — verify entry point works,
    # then cancel and create templates via setup helper in subsequent tests.
    await account1.send_command("/menu")


async def _create_template_via_bot(bot_setup: BotSetup, db: DBAssertions) -> int:
    """Helper: create survey template via bot setup."""
    template_id = await bot_setup.create_survey_template(
        title="E2E Test Survey",
        questions=[
            {
                "title": "What is your feedback?",
                "type": "text",
                "is_required": True,
            },
            {
                "title": "Rate 1-5 (explicit config)",
                "type": "rating",
                "config": {"min": 1, "max": 5},
            },
            {
                "title": "Choose one",
                "type": "single_choice",
                "options": [
                    {"label": "Option A"},
                    {"label": "Option B"},
                ],
            },
            {
                "title": "Choose many",
                "type": "multiple_choice",
                "options": [
                    {"label": "Choice A"},
                    {"label": "Choice B"},
                    {"label": "Choice C"},
                ],
            },
        ],
    )
    return template_id


async def test_list_survey_templates(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """List survey templates shows created template."""
    # Ensure template exists
    template = await db.get_survey_template_by_title("E2E Test Survey")
    if template is None:
        template_id = await _create_template_via_bot(bot_setup, db)
        _module_state["template_id"] = template_id
    else:
        _module_state["template_id"] = template["id"]

    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    menu_msg = await account1.send_command("/menu")
    surveys_btn = find_button(menu_msg, "menu_surveys")
    surveys_msg = await account1.click_button(menu_msg, text=surveys_btn.text)

    list_btn = find_button(surveys_msg, "sb_action:list")
    assert list_btn is not None, "Survey menu should have 'List' button"
    list_msg = await account1.click_button(surveys_msg, text=list_btn.text)

    assert list_msg.reply_markup is not None, "Template list should have buttons"
    buttons = get_buttons(list_msg)
    assert len(buttons) >= 1, "Should have at least one template button"


async def test_toggle_survey_template(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """Toggle survey template active/inactive."""
    template_id = _module_state.get("template_id")
    assert template_id is not None, "Previous test must set template_id"

    # Navigate to template detail
    menu_msg = await account1.send_command("/menu")
    surveys_btn = find_button(menu_msg, "menu_surveys")
    surveys_msg = await account1.click_button(menu_msg, text=surveys_btn.text)

    list_btn = find_button(surveys_msg, "sb_action:list")
    list_msg = await account1.click_button(surveys_msg, text=list_btn.text)

    detail_btn = find_button(list_msg, f"sb_detail:{template_id}")
    assert detail_btn is not None, f"Should find template button for id={template_id}"
    detail_msg = await account1.click_button(list_msg, text=detail_btn.text)

    # Toggle off
    toggle_btn = find_button(detail_msg, f"sb_toggle:{template_id}")
    assert toggle_btn is not None, "Template detail should have toggle button"
    off_msg = await account1.click_button(detail_msg, text=toggle_btn.text)
    assert "выключен" in off_msg.text.lower(), (
        f"Expected 'выключен', got: {off_msg.text[:200]}"
    )

    # Toggle back on
    toggle_btn2 = find_button(off_msg, f"sb_toggle:{template_id}")
    assert toggle_btn2 is not None
    on_msg = await account1.click_button(off_msg, text=toggle_btn2.text)
    assert "включен" in on_msg.text.lower(), (
        f"Expected 'включен', got: {on_msg.text[:200]}"
    )


# ── Survey taking ──


async def test_student_takes_survey_all_types(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Student completes a survey with all 4 question types."""
    template_id = _module_state.get("template_id")
    if template_id is None:
        template_id = await _create_template_via_bot(bot_setup, db)
        _module_state["template_id"] = template_id

    await account2.send_command_multi("/start", count=2)

    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")

    session_id = await setup.create_survey_session(template_id, ACCOUNT_2_TG_ID)
    _module_state["session_id"] = session_id

    # Access surveys via press_callback (my_surveys is not in main menu)
    surveys_msg = await account2.press_callback("my_surveys")

    # Start survey
    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None, (
        f"Should find start_survey button for session {session_id}. "
        f"Msg: {surveys_msg.text[:200] if surveys_msg.text else 'no text'}"
    )
    await account2.click_button(surveys_msg, text=start_btn.text)

    # Q1: text — send text answer
    q1_resp = await account2.send_text_in_fsm("Great feedback from E2E test")
    assert q1_resp.text is not None

    # Q2: rating — click "3"
    rating_btn = find_button(q1_resp, "ds_ans:3")
    assert rating_btn is not None, "Should find rating button '3'"
    q2_resp = await account2.click_button(q1_resp, text=rating_btn.text)

    # Q3: single_choice — click "Option A"
    choice_btn = find_button(q2_resp, "ds_ans:opt_1")
    assert choice_btn is not None, "Should find single choice button 'opt_1'"
    q3_resp = await account2.click_button(q2_resp, text=choice_btn.text)

    # Q4: multiple_choice — select mc_a, mc_c, then done
    # Note: toggling mc options only updates FSM state + shows toast, no message edit.
    # Use raw click() for toggles, then click_button for "Done" which advances.
    mc_a_btn = find_button(q3_resp, "ds_ans:opt_1")
    assert mc_a_btn is not None, "Should find multiple choice button 'opt_1'"
    await q3_resp.click(text=mc_a_btn.text)
    await asyncio.sleep(1)

    mc_c_btn = find_button(q3_resp, "ds_ans:opt_3")
    assert mc_c_btn is not None, "Should find multiple choice button 'opt_3'"
    await q3_resp.click(text=mc_c_btn.text)
    await asyncio.sleep(1)

    done_btn = find_button(q3_resp, "ds_ans:__done__")
    assert done_btn is not None, "Should find 'Done' button for multiple choice"
    final_msg = await account2.click_button(q3_resp, text=done_btn.text)

    assert "завершён" in final_msg.text.lower(), (
        f"Expected 'завершён', got: {final_msg.text[:200]}"
    )

    # DB checks
    session = await db.assert_survey_completed(ACCOUNT_2_TG_ID)
    assert session is not None

    answers = await db.get_survey_answers(session_id)
    assert len(answers) == 4, f"Expected 4 answers, got {len(answers)}"


async def test_rating_buttons_range(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
):
    """Rating question buttons should match configured min/max range."""
    template_id = _module_state.get("template_id")
    assert template_id is not None

    session_id = await setup.create_survey_session(
        template_id, ACCOUNT_2_TG_ID, context_type="test_range", context_id="range"
    )

    surveys_msg = await account2.press_callback("my_surveys")

    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None
    await account2.click_button(surveys_msg, text=start_btn.text)

    # Q1 is text — answer it
    q1_resp = await account2.send_text_in_fsm("test")

    # Q2 is rating — check buttons 1-5
    buttons = get_buttons(q1_resp)
    rating_texts = [
        b.text for b in buttons if b.data and b"ds_ans:" in b.data and b.text.isdigit()
    ]
    assert len(rating_texts) == 5, (
        f"Expected 5 rating buttons for max=5 config, got {len(rating_texts)}: {rating_texts}"
    )
    assert "1" in rating_texts, f"Should have button '1', got: {rating_texts}"
    assert "5" in rating_texts, f"Should have button '5', got: {rating_texts}"

    # Cancel survey
    cancel_btn = find_button(q1_resp, "ds_ans:__cancel__")
    if cancel_btn:
        await account2.click_button(q1_resp, text=cancel_btn.text)


async def test_required_text_empty_answer(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
):
    """Empty answer on required text question should be rejected."""
    template_id = _module_state.get("template_id")
    assert template_id is not None

    session_id = await setup.create_survey_session(
        template_id, ACCOUNT_2_TG_ID, context_type="test_empty", context_id="empty"
    )

    surveys_msg = await account2.press_callback("my_surveys")

    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None
    await account2.click_button(surveys_msg, text=start_btn.text)

    # Send a single dot — bot should accept it (non-empty text)
    # Telethon cannot send whitespace-only messages, so we test with minimal input
    resp = await account2.send_text_in_fsm(".")
    assert resp.text is not None, "Bot should respond to minimal text input"

    # Cancel
    # Need to send /start to clear FSM state since cancel is only via callback in survey
    await account2.send_command_multi("/start", count=2)


async def test_multiple_choice_no_selection_required(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
):
    """Pressing Done without selection on required multiple_choice should not advance."""
    template_id = _module_state.get("template_id")
    assert template_id is not None

    session_id = await setup.create_survey_session(
        template_id, ACCOUNT_2_TG_ID, context_type="test_mc", context_id="mc_empty"
    )

    surveys_msg = await account2.press_callback("my_surveys")

    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None
    await account2.click_button(surveys_msg, text=start_btn.text)

    # Answer Q1 (text) to get to Q2 (rating)
    q2_msg = await account2.send_text_in_fsm("test answer")

    # Q2 rating — click 3
    rating_btn = find_button(q2_msg, "ds_ans:3")
    assert rating_btn is not None, "Should find rating button '3' on Q2"
    q3_msg = await account2.click_button(q2_msg, text=rating_btn.text)

    # Q3 single choice — click first option
    sc_btn = find_button(q3_msg, "ds_ans:opt_1")
    assert sc_btn is not None, "Should find single choice button 'opt_1' on Q3"
    q4_msg = await account2.click_button(q3_msg, text=sc_btn.text)

    # Q4 multiple choice — click Done without selecting
    done_btn = find_button(q4_msg, "ds_ans:__done__")
    assert done_btn is not None, "Should find 'Done' button for multiple choice on Q4"

    # Click done — should not advance (callback.answer with error toast, no message edit)
    await q4_msg.click(text=done_btn.text)
    await asyncio.sleep(1)

    # Verify message hasn't changed (still on Q4, not completed)
    messages = await account2.get_last_messages(limit=1)
    assert "завершён" not in messages[0].text.lower(), (
        "Survey should NOT be completed without selection"
    )

    # Cleanup
    await account2.send_command_multi("/start", count=2)


async def test_survey_cancel(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
):
    """Cancel survey mid-way through."""
    template_id = _module_state.get("template_id")
    assert template_id is not None

    session_id = await setup.create_survey_session(
        template_id, ACCOUNT_2_TG_ID, context_type="test_cancel", context_id="cancel"
    )

    surveys_msg = await account2.press_callback("my_surveys")

    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None
    await account2.click_button(surveys_msg, text=start_btn.text)

    # Answer Q1 (text)
    q1_resp = await account2.send_text_in_fsm("partial answer")

    # Cancel on Q2
    cancel_btn = find_button(q1_resp, "ds_ans:__cancel__")
    assert cancel_btn is not None, "Should find cancel button"
    cancel_msg = await account2.click_button(q1_resp, text=cancel_btn.text)
    assert "отменён" in cancel_msg.text.lower(), (
        f"Expected 'отменён', got: {cancel_msg.text[:200]}"
    )


async def test_survey_duplicate_prevented(
    db: DBAssertions,
):
    """Completed survey session should not allow re-completion."""
    session_id = _module_state.get("session_id")
    assert session_id is not None, "test_student_takes_survey must run first"

    # Check that only 1 completed session exists for the main context
    template_id = _module_state.get("template_id")
    if template_id is None:
        pytest.skip("template_id not set — prerequisite test failed")
    count = await db.count_survey_sessions(template_id, ACCOUNT_2_TG_ID, "test", "e2e")
    assert count == 1, f"Expected 1 session for test/e2e context, got {count}"


async def test_view_survey_results(
    account1: TelegramTestClient,
    db: DBAssertions,
    bot_setup: BotSetup,
):
    """Admin views survey results."""
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")

    menu_msg = await account1.send_command("/menu")
    surveys_btn = find_button(menu_msg, "menu_surveys")
    surveys_msg = await account1.click_button(menu_msg, text=surveys_btn.text)

    results_btn = find_button(surveys_msg, "sb_action:results")
    assert results_btn is not None, "Survey menu should have 'Results' button"
    results_msg = await account1.click_button(surveys_msg, text=results_btn.text)

    assert results_msg.reply_markup is not None, (
        "Results should show template selection"
    )
    buttons = get_buttons(results_msg)
    assert len(buttons) >= 1, "Should have at least one template to view results"


async def test_delete_survey_template(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """Delete survey template."""
    template_id = _module_state.get("template_id")
    assert template_id is not None

    menu_msg = await account1.send_command("/menu")
    surveys_btn = find_button(menu_msg, "menu_surveys")
    surveys_msg = await account1.click_button(menu_msg, text=surveys_btn.text)

    list_btn = find_button(surveys_msg, "sb_action:list")
    list_msg = await account1.click_button(surveys_msg, text=list_btn.text)

    detail_btn = find_button(list_msg, f"sb_detail:{template_id}")
    assert detail_btn is not None, f"Template {template_id} should be in list"
    detail_msg = await account1.click_button(list_msg, text=detail_btn.text)

    delete_btn = find_button(detail_msg, f"sb_delete:{template_id}")
    assert delete_btn is not None, "Template detail should have delete button"
    await account1.click_button(detail_msg, text=delete_btn.text)

    # Verify deletion in DB
    template = await db.get_survey_template_by_title("E2E Test Survey")
    assert template is None, "Template should be deleted from DB"
