import asyncio
import os
from datetime import datetime, timezone

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

UTC = timezone.utc

_module_state: dict = {}


# ── Inline analytics: alerts created on survey completion ──


async def test_low_score_alert_created(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Student fills survey with low rating -> SurveyAlert(low_score) in DB."""
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "admin")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")

    template_id = await bot_setup.create_survey_template(
        title="E2E Alert Rating",
        slug="e2e_alert_rating",
        questions=[
            {
                "title": "Rate your experience",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            },
        ],
    )
    _module_state["alert_template_id"] = template_id

    session_id = await setup.create_survey_session(
        template_id, ACCOUNT_2_TG_ID, context_type="test", context_id="alert1"
    )
    _module_state["low_score_session_id"] = session_id

    # Account2: open surveys -> start -> answer with low score (2 <= 4 default threshold)
    surveys_msg = await account2.press_callback("my_surveys")
    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None, f"Should find start button for session {session_id}"
    q1_msg = await account2.click_button(surveys_msg, text=start_btn.text)

    rating_btn = find_button(q1_msg, "ds_ans:2")
    assert rating_btn is not None, "Should find rating button '2'"
    final_msg = await account2.click_button(q1_msg, text=rating_btn.text)

    assert "завершён" in final_msg.text.lower(), (
        f"Expected 'завершён', got: {final_msg.text[:200]}"
    )

    # Verify alert in DB
    alerts = await db.get_survey_alerts_by_type(session_id, "low_score")
    assert len(alerts) >= 1, f"Expected low_score alert, got {len(alerts)} alerts"
    alert = alerts[0]
    assert alert["details"]["score"] == 2
    assert alert["notified"] is False
    _module_state["low_score_alert_id"] = alert["id"]


async def test_mentor_not_recommend_alert(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Mentor passes greeting_mentor_feedback, chooses 'No' -> alert(mentor_not_recommend)."""
    template_id = await bot_setup.create_survey_template(
        title="E2E Greeting Mentor Feedback",
        slug="greeting_mentor_feedback",
        questions=[
            {
                "title": "Rate the student",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            },
            {
                "title": "Would you recommend taking this student?",
                "type": "single_choice",
                "options": [
                    {"value": "yes", "label": "Да"},
                    {"value": "no", "label": "Нет"},
                ],
            },
        ],
    )
    _module_state["mentor_feedback_template_id"] = template_id

    session_id = await setup.create_survey_session(
        template_id,
        ACCOUNT_1_TG_ID,
        context_type="test",
        context_id=f"2026-W14:{ACCOUNT_2_TG_ID}",
    )
    _module_state["mentor_feedback_session_id"] = session_id

    # Account1: open surveys -> start -> rate 8 -> choose "no"
    surveys_msg = await account1.press_callback("my_surveys")
    start_btn = find_button(surveys_msg, f"ds_start:{session_id}")
    assert start_btn is not None, f"Should find start button for session {session_id}"
    q1_msg = await account1.click_button(surveys_msg, text=start_btn.text)

    # Q1: rating = 8
    rating_btn = find_button(q1_msg, "ds_ans:8")
    assert rating_btn is not None, "Should find rating button '8'"
    q2_msg = await account1.click_button(q1_msg, text=rating_btn.text)

    # Q2: single_choice = "no"
    no_btn = find_button(q2_msg, "ds_ans:no")
    assert no_btn is not None, "Should find choice button 'no'"
    final_msg = await account1.click_button(q2_msg, text=no_btn.text)

    assert "завершён" in final_msg.text.lower(), (
        f"Expected 'завершён', got: {final_msg.text[:200]}"
    )

    # Verify mentor_not_recommend alert
    alerts_mnr = await db.get_survey_alerts_by_type(session_id, "mentor_not_recommend")
    assert len(alerts_mnr) >= 1, "Expected mentor_not_recommend alert"

    # Verify NO low_score alert (rating 8 > threshold 4)
    alerts_ls = await db.get_survey_alerts_by_type(session_id, "low_score")
    assert len(alerts_ls) == 0, (
        f"Should NOT have low_score alert for rating=8, got {len(alerts_ls)}"
    )


# ── Celery-dependent: alert + escalation pipeline (parallelized) ──


async def test_setup_all_celery_conditions(
    db: DBAssertions, setup: E2ESetup, bot_setup: BotSetup
):
    """Создаём 3 escalation-сессии параллельно, чтобы затем ждать их одновременно."""
    template_id = _module_state["alert_template_id"]

    # Создаём 3 сессии параллельно (независимые INSERT'ы)
    s_reminder, s_mentor, s_escalate = await asyncio.gather(
        setup.create_survey_session(template_id, ACCOUNT_2_TG_ID, "esc", "r"),
        setup.create_survey_session(template_id, ACCOUNT_2_TG_ID, "esc", "m"),
        setup.create_survey_session(template_id, ACCOUNT_2_TG_ID, "esc", "e"),
    )

    # Backdate параллельно
    await asyncio.gather(
        setup.backdate_session(s_reminder, hours_ago=25),
        setup.backdate_session(s_mentor, hours_ago=73),
        setup.backdate_session(s_escalate, hours_ago=97),
    )

    # mentor/mentee нужны для проверки уведомлений
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    # Для 73h-сессии: предзаполняем reminder_sent_at (иначе Celery попытается сначала сделать reminder)
    # Для 97h-сессии: предзаполняем оба предшествующих поля
    await asyncio.gather(
        setup.set_session_field(
            s_mentor, "reminder_sent_at", datetime(2026, 1, 1, tzinfo=UTC)
        ),
        setup.set_session_field(
            s_escalate, "reminder_sent_at", datetime(2026, 1, 1, tzinfo=UTC)
        ),
    )
    await setup.set_session_field(
        s_escalate, "mentor_notified_at", datetime(2026, 1, 1, tzinfo=UTC)
    )

    # Роли для получателей эскалации
    await asyncio.gather(
        bot_setup.set_user_cohort(ACCOUNT_2_TG_ID, "Status", "Study"),
        bot_setup.set_user_role(ACCOUNT_1_TG_ID, "education_lead"),
    )

    _module_state["escalation_session_id"] = s_reminder
    _module_state["mentor_session_id"] = s_mentor
    _module_state["escalate_session_id"] = s_escalate


async def test_all_celery_conditions_resolved(
    db: DBAssertions,
    wait_for_all_celery,
):
    """Ждём все Celery-условия одновременно: alert + 3 ступени эскалации."""
    low_score_session_id = _module_state["low_score_session_id"]
    s_reminder = _module_state["escalation_session_id"]
    s_mentor = _module_state["mentor_session_id"]
    s_escalate = _module_state["escalate_session_id"]

    async def check_alert_notified():
        alerts = await db.get_survey_alerts_by_type(low_score_session_id, "low_score")
        return alerts and alerts[0]["notified"] is True

    async def check_reminder_sent():
        fields = await db.get_session_escalation_fields(s_reminder)
        return fields and fields["reminder_sent_at"] is not None

    async def check_mentor_notified():
        fields = await db.get_session_escalation_fields(s_mentor)
        return fields and fields["mentor_notified_at"] is not None

    async def check_escalated():
        fields = await db.get_session_escalation_fields(s_escalate)
        return fields and fields["escalated_at"] is not None

    await wait_for_all_celery(
        check_alert_notified,
        check_reminder_sent,
        check_mentor_notified,
        check_escalated,
        max_wait=600,
        labels=["alert_notified", "reminder_25h", "mentor_notify_73h", "escalate_97h"],
        skip_msg="Celery tasks (process_alerts + escalate_pending_sessions) не ответили",
    )


async def test_non_escalatable_session_skipped(
    db: DBAssertions,
    setup: E2ESetup,
):
    """Session with is_escalatable=false does not get reminder."""
    template_id = _module_state.get("alert_template_id")
    assert template_id is not None, "Previous tests must set alert_template_id"

    session_id = await setup.create_survey_session(
        template_id, ACCOUNT_2_TG_ID, context_type="esc", context_id="skip"
    )
    await setup.backdate_session(session_id, hours_ago=25)
    await setup.set_session_field(session_id, "is_escalatable", False)

    # Wait 1 escalation check cycle (task runs every 1-2 min in test env)
    await asyncio.sleep(70)

    fields = await db.get_session_escalation_fields(session_id)
    assert fields is not None, f"Session {session_id} not found"
    assert fields["reminder_sent_at"] is None, (
        "Non-escalatable session should NOT receive a reminder"
    )
