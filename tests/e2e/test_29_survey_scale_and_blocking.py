"""E2E tests for survey scale 1-10, alert thresholds, block middleware, and hard reminders."""

import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state: dict = {}
# Keys: template_id, msr_template_id


# ── Test 1: Rating scale 1-10 default ──


async def test_rating_scale_1_to_10_default(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Rating buttons should show 1-10 when template config is empty (runtime default)."""
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID)

    template_id = await setup.create_survey_template(
        title="E2E Scale 10 Test",
        slug="e2e_scale_10",
        questions=[
            {
                "title": "Rate overall experience",
                "type": "rating",
                "config": {},
            }
        ],
    )
    _module_state["template_id"] = template_id

    session_id = await setup.create_survey_session(template_id, ACCOUNT_2_TG_ID)

    surveys_msg = await account2.press_callback("my_surveys")
    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None, f"Should find start button for session {session_id}"
    q1_msg = await account2.click_button(surveys_msg, text=start_btn.text)

    # Verify 10 rating buttons with texts "1" through "10"
    buttons = get_buttons(q1_msg)
    rating_btns = [
        b
        for b in buttons
        if b.data and b.data.decode().startswith("ds_ans:") and b.text.isdigit()
    ]
    rating_texts = [b.text for b in rating_btns]
    assert len(rating_btns) == 10, (
        f"Expected 10 rating buttons, got {len(rating_btns)}: {rating_texts}"
    )
    for i in range(1, 11):
        assert str(i) in rating_texts, (
            f"Button '{i}' missing from rating buttons: {rating_texts}"
        )

    # Verify layout: 2 rows of 5 buttons
    rows = q1_msg.reply_markup.rows
    rating_rows = [
        row
        for row in rows
        if any(
            b.data and b.data.decode().startswith("ds_ans:") and b.text.isdigit()
            for b in row.buttons
        )
    ]
    assert len(rating_rows) == 2, (
        f"Expected 2 rows of rating buttons, got {len(rating_rows)}"
    )
    assert len(rating_rows[0].buttons) == 5, (
        f"First row should have 5 buttons, got {len(rating_rows[0].buttons)}"
    )
    assert len(rating_rows[1].buttons) == 5, (
        f"Second row should have 5 buttons, got {len(rating_rows[1].buttons)}"
    )

    # Complete the survey by clicking "10"
    btn_10 = find_button(q1_msg, "ds_ans:10")
    assert btn_10 is not None, "Should find rating button '10'"
    final_msg = await account2.click_button(q1_msg, text=btn_10.text)
    assert "завершён" in final_msg.text.lower(), (
        f"Expected 'завершён', got: {final_msg.text[:200]}"
    )


# ── Test 2: mentor_self_review threshold ──


async def test_mentor_self_review_threshold_6(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """score=6 → low_score alert, score=7 → no alert (threshold is 6 inclusive)."""
    await account1.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)

    template_id = await setup.create_survey_template(
        title="E2E Mentor Self Review",
        slug="mentor_self_review",
        questions=[
            {
                "title": "Rate your mentoring",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            }
        ],
    )
    _module_state["msr_template_id"] = template_id

    # --- Subtest A: score=6 → should trigger low_score alert ---
    s1 = await setup.create_survey_session(
        template_id,
        ACCOUNT_1_TG_ID,
        context_type="self_review",
        context_id="e2e_a",
    )

    surveys_msg = await account1.press_callback("my_surveys")
    start_btn = find_button(surveys_msg, f"ds_start:{s1}")
    assert start_btn is not None, f"Should find start button for session {s1}"
    q1_msg = await account1.click_button(surveys_msg, text=start_btn.text)

    btn_6 = find_button(q1_msg, "ds_ans:6")
    assert btn_6 is not None, "Should find rating button '6'"
    final_a = await account1.click_button(q1_msg, text=btn_6.text)
    assert "завершён" in final_a.text.lower(), (
        f"Expected 'завершён', got: {final_a.text[:200]}"
    )

    alerts_a = await db.get_survey_alerts_by_type(s1, "low_score")
    assert len(alerts_a) >= 1, (
        f"Score 6 should trigger low_score alert (threshold=6), got {len(alerts_a)}"
    )

    # --- Subtest B: score=7 → should NOT trigger low_score alert ---
    s2 = await setup.create_survey_session(
        template_id,
        ACCOUNT_1_TG_ID,
        context_type="self_review",
        context_id="e2e_b",
    )

    surveys_msg2 = await account1.press_callback("my_surveys")
    start_btn2 = find_button(surveys_msg2, f"ds_start:{s2}")
    assert start_btn2 is not None, f"Should find start button for session {s2}"
    q1_msg2 = await account1.click_button(surveys_msg2, text=start_btn2.text)

    btn_7 = find_button(q1_msg2, "ds_ans:7")
    assert btn_7 is not None, "Should find rating button '7'"
    final_b = await account1.click_button(q1_msg2, text=btn_7.text)
    assert "завершён" in final_b.text.lower(), (
        f"Expected 'завершён', got: {final_b.text[:200]}"
    )

    alerts_b = await db.get_survey_alerts_by_type(s2, "low_score")
    assert len(alerts_b) == 0, (
        f"Score 7 should NOT trigger low_score alert (threshold=6), "
        f"got {len(alerts_b)} alerts"
    )


# ── Test 3: Survey block middleware ──


async def test_survey_block_middleware(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
):
    """Pending survey blocks /menu; completing it unblocks."""
    template_id = _module_state.get("template_id")
    assert template_id is not None, "test_rating_scale_1_to_10_default must run first"

    session_id = await setup.create_survey_session(
        template_id,
        ACCOUNT_2_TG_ID,
        context_type="block_test",
        context_id="e2e_block",
    )

    # /menu should be blocked
    block_msg = await account2.send_command("/menu")
    assert "незаполненный опрос" in block_msg.text.lower(), (
        f"Expected block message with 'незаполненный опрос', got: {block_msg.text[:300]}"
    )

    # Whitelist: "Перейти к опросам" button should be present and work
    surveys_btn = find_button(block_msg, "my_surveys")
    assert surveys_btn is not None, (
        "Block message should have 'Перейти к опросам' button"
    )
    surveys_msg = await account2.click_button(block_msg, text=surveys_btn.text)

    # Should see the pending survey start button
    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None, (
        f"Survey list should have start button for session {session_id}"
    )

    # Complete the survey
    q1_msg = await account2.click_button(surveys_msg, text=start_btn.text)
    rating_btns = [
        b
        for b in get_buttons(q1_msg)
        if b.data and b.data.decode().startswith("ds_ans:") and b.text.isdigit()
    ]
    assert len(rating_btns) > 0, "Should have rating buttons"
    final_msg = await account2.click_button(q1_msg, text=rating_btns[0].text)
    assert "завершён" in final_msg.text.lower(), (
        f"Expected 'завершён', got: {final_msg.text[:200]}"
    )

    # /menu should now work normally (cache invalidated on completion)
    menu_msg = await account2.send_command("/menu")
    assert "незаполненный опрос" not in menu_msg.text.lower(), (
        f"Menu should NOT be blocked after completing survey, got: {menu_msg.text[:300]}"
    )


# ── Test 4: Hard reminder text after 24h ──


async def test_hard_reminder_text(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    trigger_task,
    wait_for_celery,
):
    """24h-old pending session → hard reminder with escalation warning text."""
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    template_id = _module_state.get("template_id")
    assert template_id is not None, "test_rating_scale_1_to_10_default must run first"

    session_id = await setup.create_survey_session(
        template_id,
        ACCOUNT_2_TG_ID,
        context_type="reminder_test",
        context_id="e2e_reminder",
    )
    await setup.backdate_session(session_id, hours_ago=25)

    marker = await account2.snapshot_last_message_id()

    await trigger_task("surveys.check_escalations")

    reminder_msg = await wait_for_celery(
        lambda: account2.try_get_message_after(marker),
        skip_msg="Escalation task did not send reminder",
    )

    text = reminder_msg.text.lower()
    assert "незаполненный опрос" in text, (
        f"Reminder should mention 'Незаполненный опрос', got: {reminder_msg.text[:300]}"
    )
    assert "обязательная часть программы" in text, (
        f"Reminder should mention 'обязательная часть программы', "
        f"got: {reminder_msg.text[:300]}"
    )
    assert "информация будет передана вашему ментору" in text, (
        f"Reminder should mention mentor escalation, got: {reminder_msg.text[:300]}"
    )

    # Verify DB escalation field
    esc = await db.get_session_escalation_fields(session_id)
    assert esc is not None, "Session should exist"
    assert esc["reminder_sent_at"] is not None, (
        "reminder_sent_at should be set after 24h reminder"
    )
