import asyncio
import os

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button, get_buttons
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state = {}


async def test_start_call_saves_timestamp(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
):
    """After starting a call, call_started_at is saved in DB."""
    # Setup: mentor + mentee
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    # Create meeting via UI
    meeting_id = await bot_setup.create_meeting(
        mentor_client=account1,
        mentor_telegram_id=ACCOUNT_1_TG_ID,
        student_client=account2,
        student_telegram_id=ACCOUNT_2_TG_ID,
        description=f"[E2E-{test_run_id}] call duration test",
    )
    _module_state["meeting_id"] = meeting_id

    # Navigate: /menu -> Meetings -> Start call
    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    assert meetings_btn is not None, "Mentor menu should have meetings button"
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)

    start_btn = find_button(meetings_msg, f"meeting_start_call:{meeting_id}")
    assert start_btn is not None, (
        f"Should find start_call button for meeting {meeting_id}. "
        f"Buttons: {[(b.text, b.data.decode()) for b in get_buttons(meetings_msg)]}"
    )
    result_msg = await account1.click_button(meetings_msg, text=start_btn.text)
    assert "начат" in result_msg.text.lower(), (
        f"Expected 'начат' in response, got: {result_msg.text[:200]}"
    )

    # DB check: call_started_at should be set (not visible in UI at start)
    await db.assert_meeting_call_started_at(meeting_id)


async def test_end_call_shows_duration(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """After ending a call, the UI response contains duration info."""
    meeting_id = _module_state.get("meeting_id")
    assert meeting_id is not None, "Previous test must create a meeting"

    result_msg = await account1.send_command("/end_call")
    assert result_msg.text is not None, "Expected response from /end_call"

    text = result_msg.text.lower()

    # Should contain "завершён"
    assert "завершён" in text, (
        f"Expected 'завершён' in response, got: {result_msg.text[:300]}"
    )

    # Should contain "длительность:" with an actual value (not "—")
    assert "длительность:" in text, (
        f"Expected 'Длительность:' in response, got: {result_msg.text[:300]}"
    )
    assert "длительность: —" not in text, (
        f"Duration should be computed, not '—'. Got: {result_msg.text[:300]}"
    )

    # Should contain "мин" (format "X мин" or "Xч Yмин")
    assert "мин" in text, (
        f"Expected 'мин' in duration format, got: {result_msg.text[:300]}"
    )

    # DB check
    await db.assert_meeting_call_status(meeting_id, "завершён")


async def test_post_call_survey_no_duration_question(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    test_run_id: str,
    wait_for_celery,
):
    """Post-call survey (post_call_student) does not contain a duration question."""
    # Get seeded template id
    template = await db.get_survey_template_by_slug("post_call_student")
    assert template is not None, "Seeded template 'post_call_student' not found"
    template_id = template["id"]

    # Create trigger: call_ended -> send_survey(post_call_student) to event_students
    rule_id = await bot_setup.create_trigger_rule(
        name=f"[E2E-{test_run_id}] call_ended_survey",
        trigger_type="call_ended",
        action_type="send_survey",
        recipient_type="event_students",
        action_config={"survey_template_id": template_id},
    )
    _module_state["trigger_rule_id"] = rule_id

    # Create a new meeting via UI
    meeting_id = await bot_setup.create_meeting(
        mentor_client=account1,
        mentor_telegram_id=ACCOUNT_1_TG_ID,
        student_client=account2,
        student_telegram_id=ACCOUNT_2_TG_ID,
        description=f"[E2E-{test_run_id}] survey duration check",
    )
    _module_state["survey_meeting_id"] = meeting_id

    # Start call via UI
    menu_msg = await account1.send_command("/menu")
    meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
    meetings_msg = await account1.click_button(menu_msg, text=meetings_btn.text)
    start_btn = find_button(meetings_msg, f"meeting_start_call:{meeting_id}")
    assert start_btn is not None, (
        f"Should find start_call button for meeting {meeting_id}"
    )
    await account1.click_button(meetings_msg, text=start_btn.text)

    # Snapshot before end_call — mentee will receive the survey notification
    snapshot_id = await account2.snapshot_last_message_id()

    # End call via UI
    await account1.send_command("/end_call")

    # Wait for mentee to receive the survey notification (via Celery trigger)
    survey_notif = await wait_for_celery(
        lambda: account2.try_get_message_after(snapshot_id),
        max_wait=60,
        interval=3,
        skip_msg="Survey notification not received by mentee",
    )

    # Start the survey: click ds_start button
    start_survey_btn = find_button(survey_notif, "ds_start:")
    assert start_survey_btn is not None, (
        f"Mentee should receive survey with ds_start button. "
        f"Buttons: {[(b.text, b.data.decode() if b.data else '') for b in get_buttons(survey_notif)]}"
    )
    first_q_msg = await account2.click_button(
        survey_notif, data=start_survey_btn.data.decode()
    )

    # First question should be "Стиль общения ментора", NOT "Длительность"
    assert first_q_msg.text is not None, "First question message should have text"
    q_text = first_q_msg.text.lower()
    assert "стиль общения" in q_text, (
        f"First question should be 'Стиль общения ментора', got: {first_q_msg.text[:200]}"
    )
    assert "длительность" not in q_text, (
        f"Survey should NOT contain a duration question, got: {first_q_msg.text[:200]}"
    )

    # Cancel survey to avoid polluting data
    cancel_btn = find_button(first_q_msg, "ds_ans:__cancel__")
    if cancel_btn:
        await account2.click_button(first_q_msg, data=cancel_btn.data.decode())
