from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.tasks.survey_escalation import _check_survey_escalations_async


def _session(
    respondent_id,
    registered_at=None,
    reminder_sent_at=None,
    mentor_notified_at=None,
    escalated_at=None,
):
    return SimpleNamespace(
        id=1,
        respondent_id=respondent_id,
        respondent=SimpleNamespace(
            telegram_id=respondent_id,
            registered_at=registered_at,
            name="Test",
        ),
        created_at=datetime.now(timezone.utc) - timedelta(hours=25),
        template=SimpleNamespace(title="Test Survey"),
        reminder_sent_at=reminder_sent_at,
        mentor_notified_at=mentor_notified_at,
        escalated_at=escalated_at,
    )


async def test_skips_placeholder_respondent():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    session = _session(respondent_id=-1)

    with (
        patch("src.tasks.survey_escalation.celery_db"),
        patch("src.tasks.survey_escalation.get_worker_bot", lambda: bot),
        patch(
            "src.dao.survey_session.SurveySessionDAO.get_overdue_sessions",
            AsyncMock(return_value=[session]),
        ),
        patch(
            "src.dao.survey_session.SurveySessionDAO.update_escalation_field",
            AsyncMock(),
        ),
    ):
        await _check_survey_escalations_async()

    bot.send_message.assert_not_awaited()


async def test_skips_unregistered_respondent():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    session = _session(respondent_id=100, registered_at=None)

    with (
        patch("src.tasks.survey_escalation.celery_db"),
        patch("src.tasks.survey_escalation.get_worker_bot", lambda: bot),
        patch(
            "src.dao.survey_session.SurveySessionDAO.get_overdue_sessions",
            AsyncMock(return_value=[session]),
        ),
        patch(
            "src.dao.survey_session.SurveySessionDAO.update_escalation_field",
            AsyncMock(),
        ),
    ):
        await _check_survey_escalations_async()

    bot.send_message.assert_not_awaited()


async def test_sends_reminder_to_registered_respondent():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    session = _session(
        respondent_id=100,
        registered_at=datetime.now(timezone.utc),
    )

    with (
        patch("src.tasks.survey_escalation.celery_db"),
        patch("src.tasks.survey_escalation.get_worker_bot", lambda: bot),
        patch(
            "src.dao.survey_session.SurveySessionDAO.get_overdue_sessions",
            AsyncMock(return_value=[session]),
        ),
        patch(
            "src.dao.survey_session.SurveySessionDAO.update_escalation_field",
            AsyncMock(),
        ) as update_field,
    ):
        await _check_survey_escalations_async()

    bot.send_message.assert_awaited_once()
    update_field.assert_awaited()
