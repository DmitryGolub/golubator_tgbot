"""Advanced survey alert tests: delta_decline and cross_mismatch.

Both tests require historical completed sessions (direct DB inserts) to set up
the required pattern, plus one UI-driven session to trigger the alert logic.
"""

import os
from datetime import datetime, timedelta, timezone

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.buttons import find_button
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

UTC = timezone.utc


async def test_delta_decline_alert(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """3 consecutive sessions with declining scores → delta_decline alert created.

    DELTA_COUNTS["weekly_mentor_per_student"] = 3.
    Historical sessions: scores 8 (W10), 6 (W11).
    UI session: score 4 (W12) → series [4, 6, 8] → strictly declining.
    """
    await account1.send_command_multi("/start", count=2)
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    template_id = await setup.create_survey_template(
        title="E2E Weekly Mentor Per Student",
        slug="weekly_mentor_per_student",
        questions=[
            {
                "title": "Rate the session",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            }
        ],
    )
    q_id = await db.get_survey_question_id(template_id)

    # Historical session W10: score 8 (oldest)
    s1 = await setup.create_survey_session(
        template_id,
        ACCOUNT_1_TG_ID,
        context_type="weekly",
        context_id=f"2026-W10:{ACCOUNT_2_TG_ID}",
    )
    await setup.complete_session_with_answers(s1, [(q_id, 8)])
    await setup.set_session_field(
        s1, "completed_at", datetime.now(UTC) - timedelta(days=2)
    )

    # Historical session W11: score 6
    s2 = await setup.create_survey_session(
        template_id,
        ACCOUNT_1_TG_ID,
        context_type="weekly",
        context_id=f"2026-W11:{ACCOUNT_2_TG_ID}",
    )
    await setup.complete_session_with_answers(s2, [(q_id, 6)])
    await setup.set_session_field(
        s2, "completed_at", datetime.now(UTC) - timedelta(days=1)
    )

    # UI session W12: score 4 (most recent) — triggers delta_decline
    s3 = await setup.create_survey_session(
        template_id,
        ACCOUNT_1_TG_ID,
        context_type="weekly",
        context_id=f"2026-W12:{ACCOUNT_2_TG_ID}",
    )
    surveys_msg = await account1.press_callback("my_surveys")
    start_btn = find_button(surveys_msg, f"ds_start:{s3}")
    assert start_btn is not None, f"Should find start button for session {s3}"
    q1_msg = await account1.click_button(surveys_msg, text=start_btn.text)

    rating_btn = find_button(q1_msg, "ds_ans:4")
    assert rating_btn is not None, "Should find rating button '4'"
    final_msg = await account1.click_button(q1_msg, text=rating_btn.text)
    assert "завершён" in final_msg.text.lower(), (
        f"Expected 'завершён', got: {final_msg.text[:200]}"
    )

    alerts = await db.get_survey_alerts_by_type(s3, "delta_decline")
    assert len(alerts) >= 1, (
        f"Expected delta_decline alert after 3 declining sessions, got {len(alerts)}"
    )
    alert = alerts[0]
    assert alert["details"]["slug"] == "weekly_mentor_per_student"
    assert alert["details"]["count"] == 3


async def test_cross_mismatch_alert(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
):
    """Mentor scores 9, mentee scores 2 for same week → cross_mismatch alert (diff=7 > 4).

    CROSS_PAIRS: "search_mentee_biweekly" → "search_mentor_biweekly".
    Both sessions share context_id "2026-W14:{ACCOUNT_2_TG_ID}".
    """
    await account1.send_command_multi("/start", count=2)
    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    context_id = f"2026-W14:{ACCOUNT_2_TG_ID}"

    # Create mentor template (the paired one)
    mentor_template_id = await setup.create_survey_template(
        title="E2E Search Mentor Biweekly",
        slug="search_mentor_biweekly",
        questions=[
            {
                "title": "Rate the student",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            }
        ],
    )
    mentor_q_id = await db.get_survey_question_id(mentor_template_id)

    # Historical mentor session: score 9 (inserted directly)
    mentor_session = await setup.create_survey_session(
        mentor_template_id,
        ACCOUNT_1_TG_ID,
        context_type="search_biweekly",
        context_id=context_id,
    )
    await setup.complete_session_with_answers(mentor_session, [(mentor_q_id, 9)])

    # Create mentee template (triggers cross-validation on completion)
    mentee_template_id = await setup.create_survey_template(
        title="E2E Search Mentee Biweekly",
        slug="search_mentee_biweekly",
        questions=[
            {
                "title": "Rate your mentor",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            }
        ],
    )

    # Mentee session: account2 fills via bot UI with score 2
    mentee_session = await setup.create_survey_session(
        mentee_template_id,
        ACCOUNT_2_TG_ID,
        context_type="search_biweekly",
        context_id=context_id,
    )
    surveys_msg = await account2.press_callback("my_surveys")
    start_btn = find_button(surveys_msg, f"ds_start:{mentee_session}")
    assert start_btn is not None, (
        f"Should find start button for session {mentee_session}"
    )
    q1_msg = await account2.click_button(surveys_msg, text=start_btn.text)

    rating_btn = find_button(q1_msg, "ds_ans:2")
    assert rating_btn is not None, "Should find rating button '2'"
    final_msg = await account2.click_button(q1_msg, text=rating_btn.text)
    assert "завершён" in final_msg.text.lower(), (
        f"Expected 'завершён', got: {final_msg.text[:200]}"
    )

    # Verify cross_mismatch alert: diff = |2 - 9| = 7 > 4
    alerts = await db.get_survey_alerts_by_type(mentee_session, "cross_mismatch")
    assert len(alerts) >= 1, (
        f"Expected cross_mismatch alert (diff=7 > 4), got {len(alerts)} alerts"
    )
    alert = alerts[0]
    assert alert["details"]["diff"] > 4, (
        f"Expected diff > 4, got {alert['details']['diff']}"
    )
    assert alert["details"]["slug"] == "search_mentee_biweekly"
