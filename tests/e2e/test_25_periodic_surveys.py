"""Periodic survey distribution tests.

Covers tasks triggered manually via the TEST_MODE /test/trigger endpoint:
  - surveys.send_weekly_mentor_per_student
  - surveys.send_probation_biweekly_mentee

Setup: mentor + mentee pair with the right cohort status.
Deduplication: triggering the same task twice produces only one session.
"""

import asyncio
import datetime
import os

import pytest

from tests.e2e.helpers.bot_setup import BotSetup
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

_module_state: dict = {}


async def test_weekly_survey_sent_to_mentor(
    account1: TelegramTestClient,
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    trigger_task,
    wait_for_celery,
):
    """Triggering send_weekly_mentor_per_student creates a session and notifies the mentor."""
    await asyncio.gather(
        account1.send_command_multi("/start", count=2),
        account2.send_command_multi("/start", count=2),
    )
    await bot_setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)
    await bot_setup.set_user_cohort(ACCOUNT_2_TG_ID, "Status", "Study")

    template_id = await setup.create_survey_template(
        title="Еженедельный опрос по ученику",
        slug="weekly_mentor_per_student",
        questions=[
            {
                "title": "Оцените прогресс ученика",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            }
        ],
    )
    _module_state["weekly_template_id"] = template_id

    marker = await account1.snapshot_last_message_id()

    await trigger_task("surveys.send_weekly_mentor_per_student")

    # Wait for session to appear in DB
    await wait_for_celery(
        lambda: db.count_survey_sessions(template_id, ACCOUNT_1_TG_ID),
        max_wait=120,
        skip_msg="surveys.send_weekly_mentor_per_student не создал сессию",
    )

    # Verify mentor received Telegram notification with survey button
    notification = await account1.wait_for_message_after(marker, timeout=30)
    assert notification.reply_markup is not None, (
        "Expected inline keyboard with survey button in mentor notification"
    )
    assert "Пройти опрос" in str(
        [btn.text for row in notification.reply_markup.rows for btn in row.buttons]
    ), "Expected 'Пройти опрос' button in notification"


async def test_weekly_deduplication(
    db: DBAssertions,
    trigger_task,
    wait_for_celery,
):
    """Triggering the same weekly task again does NOT create a second session (dedup by context_id)."""
    template_id = _module_state.get("weekly_template_id")
    assert template_id is not None, "test_weekly_survey_sent_to_mentor must run first"

    count_before = await db.count_survey_sessions(template_id, ACCOUNT_1_TG_ID)
    assert count_before == 1, (
        f"Expected 1 session before dedup test, got {count_before}"
    )

    await trigger_task("surveys.send_weekly_mentor_per_student")

    # Give Celery time to process, then verify count is still 1
    import asyncio

    await asyncio.sleep(15)
    count_after = await db.count_survey_sessions(template_id, ACCOUNT_1_TG_ID)
    assert count_after == 1, (
        f"Expected deduplication: still 1 session, got {count_after}"
    )


async def test_probation_mentee_survey_sent(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    trigger_task,
    wait_for_celery,
):
    """Mentee in Probationary period receives biweekly survey when task is triggered."""
    _, week_num, _ = datetime.date.today().isocalendar()
    if week_num % 2 != 0:
        pytest.skip(
            f"Biweekly probation task skips odd ISO weeks (current week: {week_num})"
        )

    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID)
    await bot_setup.set_user_cohort(ACCOUNT_2_TG_ID, "Status", "Probationary period")

    template_id = await setup.create_survey_template(
        title="Опрос по испытательному сроку",
        slug="probation_mentee_biweekly",
        questions=[
            {
                "title": "Как проходит испытательный срок?",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            }
        ],
    )
    _module_state["probation_template_id"] = template_id

    marker = await account2.snapshot_last_message_id()

    await trigger_task("surveys.send_probation_biweekly_mentee")

    await wait_for_celery(
        lambda: db.count_survey_sessions(template_id, ACCOUNT_2_TG_ID),
        max_wait=120,
        skip_msg="surveys.send_probation_biweekly_mentee не создал сессию",
    )

    notification = await account2.wait_for_message_after(marker, timeout=30)
    assert notification.reply_markup is not None, (
        "Expected inline keyboard with survey button in mentee probation notification"
    )


async def test_no_survey_for_study_mentee(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    bot_setup: BotSetup,
    trigger_task,
):
    """Mentee in Study status should NOT receive the probation biweekly survey."""
    _, week_num, _ = datetime.date.today().isocalendar()
    if week_num % 2 != 0:
        pytest.skip(
            f"Biweekly probation task skips odd ISO weeks (current week: {week_num})"
        )

    await account2.send_command_multi("/start", count=2)
    await bot_setup.set_user_role(ACCOUNT_2_TG_ID, "student")
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID)
    await bot_setup.set_user_cohort(ACCOUNT_2_TG_ID, "Status", "Study")

    template_id = await setup.create_survey_template(
        title="Опрос по испытательному сроку",
        slug="probation_mentee_biweekly",
        questions=[
            {
                "title": "Как проходит испытательный срок?",
                "type": "rating",
                "config": {"min": 1, "max": 10},
            }
        ],
    )

    await trigger_task("surveys.send_probation_biweekly_mentee")

    import asyncio

    await asyncio.sleep(15)

    count = await db.count_survey_sessions(template_id, ACCOUNT_2_TG_ID)
    assert count == 0, (
        f"Mentee in 'Study' status should NOT receive probation survey, got {count} sessions"
    )
