from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from src.tasks.survey_escalation import _check_survey_escalations_async


def _template(*, title="Опрос", body=None, reminder_interval_minutes=None):
    return SimpleNamespace(
        title=title,
        body=body,
        reminder_interval_minutes=reminder_interval_minutes,
    )


def _session(
    *,
    id=1,
    respondent_id=100,
    created_delta=timedelta(hours=25),
    reminder_sent_delta=None,
    is_escalatable=True,
    template=None,
    respondent=None,
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=id,
        respondent_id=respondent_id,
        created_at=now - created_delta,
        reminder_sent_at=now - reminder_sent_delta if reminder_sent_delta else None,
        mentor_notified_at=None,
        escalated_at=None,
        is_escalatable=is_escalatable,
        template=template or _template(),
        respondent=respondent,
    )


async def test_skips_placeholder_respondent():
    survey_session = _session(respondent_id=-1)
    bot = AsyncMock()

    with (
        patch("src.tasks.survey_escalation.celery_db") as mock_db,
        patch("src.tasks.survey_escalation.get_worker_bot", return_value=bot),
        patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
    ):
        mock_db.return_value.__aenter__ = AsyncMock()
        mock_db.return_value.__aexit__ = AsyncMock()
        mock_session_dao.get_overdue_sessions = AsyncMock(return_value=[survey_session])
        mock_session_dao.update_escalation_field = AsyncMock()

        await _check_survey_escalations_async()

    bot.send_message.assert_not_called()
    mock_session_dao.update_escalation_field.assert_not_called()


async def test_skips_unregistered_respondent():
    survey_session = _session(
        respondent=SimpleNamespace(
            telegram_id=100,
            registered_at=None,
            name="Test",
        ),
    )
    bot = AsyncMock()

    with (
        patch("src.tasks.survey_escalation.celery_db") as mock_db,
        patch("src.tasks.survey_escalation.get_worker_bot", return_value=bot),
        patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
    ):
        mock_db.return_value.__aenter__ = AsyncMock()
        mock_db.return_value.__aexit__ = AsyncMock()
        mock_session_dao.get_overdue_sessions = AsyncMock(return_value=[survey_session])
        mock_session_dao.update_escalation_field = AsyncMock()

        await _check_survey_escalations_async()

    bot.send_message.assert_not_called()
    mock_session_dao.update_escalation_field.assert_not_called()


async def test_sends_reminder_to_registered_respondent():
    survey_session = _session(
        respondent=SimpleNamespace(
            telegram_id=100,
            registered_at=datetime.now(timezone.utc),
            name="Test",
        ),
    )
    bot = AsyncMock()

    with (
        patch("src.tasks.survey_escalation.celery_db") as mock_db,
        patch("src.tasks.survey_escalation.get_worker_bot", return_value=bot),
        patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
        patch("src.tasks.survey_escalation._notify_mentor", new_callable=AsyncMock),
    ):
        mock_db.return_value.__aenter__ = AsyncMock()
        mock_db.return_value.__aexit__ = AsyncMock()
        mock_session_dao.get_overdue_sessions = AsyncMock(return_value=[survey_session])
        mock_session_dao.update_escalation_field = AsyncMock()

        await _check_survey_escalations_async()

    bot.send_message.assert_awaited_once()
    mock_session_dao.update_escalation_field.assert_any_await(
        survey_session.id, "reminder_sent_at", ANY
    )


async def test_regular_survey_sends_one_time_reminder():
    survey_session = _session(
        template=_template(title="Обычный опрос", reminder_interval_minutes=None)
    )
    bot = AsyncMock()

    with (
        patch("src.tasks.survey_escalation.celery_db") as mock_db,
        patch("src.tasks.survey_escalation.get_worker_bot", return_value=bot),
        patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
        patch("src.tasks.survey_escalation._notify_mentor", new_callable=AsyncMock),
    ):
        mock_db.return_value.__aenter__ = AsyncMock()
        mock_db.return_value.__aexit__ = AsyncMock()
        mock_session_dao.get_overdue_sessions = AsyncMock(return_value=[survey_session])
        mock_session_dao.update_escalation_field = AsyncMock()

        await _check_survey_escalations_async()

    bot.send_message.assert_awaited_once()
    mock_session_dao.update_escalation_field.assert_any_await(
        survey_session.id, "reminder_sent_at", ANY
    )


async def test_regular_survey_does_not_repeat_generic_reminder():
    survey_session = _session(
        reminder_sent_delta=timedelta(hours=1),
        template=_template(reminder_interval_minutes=None),
    )
    bot = AsyncMock()

    with (
        patch("src.tasks.survey_escalation.celery_db") as mock_db,
        patch("src.tasks.survey_escalation.get_worker_bot", return_value=bot),
        patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
    ):
        mock_db.return_value.__aenter__ = AsyncMock()
        mock_db.return_value.__aexit__ = AsyncMock()
        mock_session_dao.get_overdue_sessions = AsyncMock(return_value=[survey_session])
        mock_session_dao.update_escalation_field = AsyncMock()

        await _check_survey_escalations_async()

    bot.send_message.assert_not_called()
    mock_session_dao.update_escalation_field.assert_not_called()


async def test_interval_survey_repeats_reminders_every_interval():
    template = _template(
        title="Фактическая длительность созвона",
        body="⏱ Напоминание: укажите фактическую длительность созвона в минутах.",
        reminder_interval_minutes=30,
    )
    first_due = _session(
        id=1,
        created_delta=timedelta(minutes=31),
        is_escalatable=False,
        template=template,
    )
    repeated_due = _session(
        id=2,
        created_delta=timedelta(hours=2),
        reminder_sent_delta=timedelta(minutes=31),
        is_escalatable=False,
        template=template,
    )
    bot = AsyncMock()

    with (
        patch("src.tasks.survey_escalation.celery_db") as mock_db,
        patch("src.tasks.survey_escalation.get_worker_bot", return_value=bot),
        patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
        patch(
            "src.tasks.survey_escalation._notify_mentor", new_callable=AsyncMock
        ) as mock_notify,
    ):
        mock_db.return_value.__aenter__ = AsyncMock()
        mock_db.return_value.__aexit__ = AsyncMock()
        mock_session_dao.get_overdue_sessions = AsyncMock(
            return_value=[first_due, repeated_due]
        )
        mock_session_dao.update_escalation_field = AsyncMock()

        await _check_survey_escalations_async()

    assert bot.send_message.await_count == 2
    mock_session_dao.update_escalation_field.assert_any_await(
        first_due.id, "reminder_sent_at", ANY
    )
    mock_session_dao.update_escalation_field.assert_any_await(
        repeated_due.id, "reminder_sent_at", ANY
    )
    mock_notify.assert_not_awaited()


async def test_not_escalatable_interval_survey_skips_mentor_and_lead_escalation():
    survey_session = _session(
        created_delta=timedelta(hours=100),
        reminder_sent_delta=timedelta(minutes=1),
        is_escalatable=False,
        template=_template(reminder_interval_minutes=30),
    )
    bot = AsyncMock()

    with (
        patch("src.tasks.survey_escalation.celery_db") as mock_db,
        patch("src.tasks.survey_escalation.get_worker_bot", return_value=bot),
        patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
        patch(
            "src.tasks.survey_escalation._notify_mentor", new_callable=AsyncMock
        ) as mock_notify,
    ):
        mock_db.return_value.__aenter__ = AsyncMock()
        mock_db.return_value.__aexit__ = AsyncMock()
        mock_session_dao.get_overdue_sessions = AsyncMock(return_value=[survey_session])
        mock_session_dao.update_escalation_field = AsyncMock()

        await _check_survey_escalations_async()

    bot.send_message.assert_not_called()
    mock_notify.assert_not_awaited()
    mock_session_dao.update_escalation_field.assert_not_called()
