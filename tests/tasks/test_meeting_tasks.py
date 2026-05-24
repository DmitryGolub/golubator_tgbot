from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.exc import IntegrityError

from tests.conftest import make_meeting, make_user
from src.models.meeting import MeetingNotificationType, ProposalStatus
from src.tasks.meeting import (
    _auto_start_due_calls_async,
    _request_due_call_durations_async,
    _send_confirmation_request,
    _send_final_reminders_async,
    _send_meeting_notification,
    _split_participants,
)


CREATOR_ID = 100
OTHER1_ID = 200
OTHER2_ID = 300
OTHER3_ID = 400


def _creator():
    return make_user(telegram_id=CREATOR_ID, name="Creator")


def _other(tid, name="Other"):
    return make_user(telegram_id=tid, name=name)


class TestSplitParticipants:
    def test_single_other(self):
        meeting = make_meeting(
            participants=[_creator(), _other(OTHER1_ID)],
            mentor_telegram_id=CREATOR_ID,
        )
        creator, others = _split_participants(meeting)
        assert creator is not None
        assert creator.telegram_id == CREATOR_ID
        assert len(others) == 1
        assert others[0].telegram_id == OTHER1_ID

    def test_multiple_others(self):
        meeting = make_meeting(
            participants=[
                _creator(),
                _other(OTHER1_ID),
                _other(OTHER2_ID),
                _other(OTHER3_ID),
            ],
            mentor_telegram_id=CREATOR_ID,
        )
        creator, others = _split_participants(meeting)
        assert creator is not None
        assert len(others) == 3
        assert {p.telegram_id for p in others} == {OTHER1_ID, OTHER2_ID, OTHER3_ID}

    def test_no_creator(self):
        meeting = make_meeting(
            participants=[_other(OTHER1_ID), _other(OTHER2_ID)],
            mentor_telegram_id=999,
        )
        creator, others = _split_participants(meeting)
        assert creator is None
        assert len(others) == 2

    def test_empty_participants(self):
        meeting = make_meeting(participants=[], mentor_telegram_id=CREATOR_ID)
        creator, others = _split_participants(meeting)
        assert creator is None
        assert others == []


class TestAutoStartDueCalls:
    def _patches(self):
        mock_db = patch("src.tasks.meeting.celery_db")
        mock_dao = patch("src.tasks.meeting.MeetingDAO")
        return mock_db, mock_dao

    async def test_no_due_meetings(self):
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.tasks.meeting.MeetingDAO") as mock_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_dao.find_due_unstarted_call_ids = AsyncMock(return_value=[])
            mock_dao.start_call = AsyncMock()

            await _auto_start_due_calls_async()

            mock_dao.find_due_unstarted_call_ids.assert_awaited_once()
            mock_dao.start_call.assert_not_called()

    async def test_starts_each_meeting_with_scheduled_at(self):
        sched1 = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
        sched2 = datetime(2026, 4, 12, 11, 0, tzinfo=timezone.utc)
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.tasks.meeting.MeetingDAO") as mock_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_dao.find_due_unstarted_call_ids = AsyncMock(
                return_value=[(1, sched1), (2, sched2)]
            )
            mock_dao.start_call = AsyncMock(
                side_effect=[make_meeting(id=1), make_meeting(id=2)]
            )

            await _auto_start_due_calls_async()

            assert mock_dao.start_call.await_count == 2
            mock_dao.start_call.assert_any_await(1, started_at=sched1)
            mock_dao.start_call.assert_any_await(2, started_at=sched2)

    async def test_integrity_error_skips_and_continues(self):
        sched1 = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
        sched2 = datetime(2026, 4, 12, 11, 0, tzinfo=timezone.utc)
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.tasks.meeting.MeetingDAO") as mock_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_dao.find_due_unstarted_call_ids = AsyncMock(
                return_value=[(1, sched1), (2, sched2)]
            )
            mock_dao.start_call = AsyncMock(
                side_effect=[
                    IntegrityError("stmt", {}, Exception("active call exists")),
                    make_meeting(id=2),
                ]
            )

            await _auto_start_due_calls_async()

            assert mock_dao.start_call.await_count == 2

    async def test_race_none_result_skipped(self):
        sched1 = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.tasks.meeting.MeetingDAO") as mock_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_dao.find_due_unstarted_call_ids = AsyncMock(return_value=[(1, sched1)])
            mock_dao.start_call = AsyncMock(return_value=None)

            # Should not raise
            await _auto_start_due_calls_async()
            mock_dao.start_call.assert_awaited_once_with(1, started_at=sched1)


class TestSendMeetingNotification:
    async def test_idempotent_second_call_skips(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()

        user = make_user(telegram_id=200, registered_at=datetime.now(timezone.utc))

        with (
            patch(
                "src.dao.meeting_notification.MeetingNotificationDAO.try_create",
                AsyncMock(return_value=(SimpleNamespace(id=1), True)),
            ) as try_create,
            patch(
                "src.dao.user.UserDAO.find_one_or_none",
                AsyncMock(return_value=user),
            ),
            patch(
                "src.tasks.meeting.safe_send_message",
                AsyncMock(return_value=True),
            ) as safe_send,
            patch(
                "src.dao.meeting_notification.MeetingNotificationDAO.mark_sent",
                AsyncMock(),
            ) as mark_sent,
        ):
            result1 = await _send_meeting_notification(
                1,
                200,
                MeetingNotificationType.confirmation_request,
                "test",
                bot=bot,
            )
            assert result1 is True
            assert try_create.await_count == 1
            assert safe_send.await_count == 1
            assert mark_sent.await_count == 1

            # Second call with same idempotency key
            try_create.return_value = (SimpleNamespace(id=1), False)
            result2 = await _send_meeting_notification(
                1,
                200,
                MeetingNotificationType.confirmation_request,
                "test",
                bot=bot,
            )
            assert result2 is False
            assert try_create.await_count == 2
            assert safe_send.await_count == 1  # no additional send
            assert mark_sent.await_count == 1

    async def test_skips_unregistered_user(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()

        with (
            patch(
                "src.dao.meeting_notification.MeetingNotificationDAO.try_create",
                AsyncMock(return_value=(SimpleNamespace(id=1), True)),
            ) as try_create,
            patch(
                "src.dao.user.UserDAO.find_one_or_none",
                AsyncMock(return_value=None),
            ),
            patch(
                "src.dao.meeting_notification.MeetingNotificationDAO.mark_failed",
                AsyncMock(),
            ) as mark_failed,
        ):
            result = await _send_meeting_notification(
                1,
                200,
                MeetingNotificationType.confirmation_request,
                "test",
                bot=bot,
            )
            assert result is False
            try_create.assert_not_awaited()
            mark_failed.assert_not_awaited()
            bot.send_message.assert_not_awaited()


class TestSendConfirmationRequest:
    async def test_sends_only_when_pending(self):
        meeting = make_meeting(
            id=1,
            participants=[_creator(), _other(200)],
            mentor_telegram_id=CREATOR_ID,
            proposal_status=ProposalStatus.pending_confirmation,
            proposed_by=CREATOR_ID,
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        with (
            patch("src.tasks.meeting._load_meeting", AsyncMock(return_value=meeting)),
            patch(
                "src.tasks.meeting._send_meeting_notification",
                AsyncMock(return_value=True),
            ) as notify,
            patch(
                "src.core.database.async_session_maker",
                MagicMock(),
            ) as session_mock,
            patch(
                "src.dao.user.UserDAO.find_one_or_none",
                AsyncMock(return_value=_creator()),
            ),
        ):
            session_instance = AsyncMock()
            session_mock.return_value.__aenter__ = AsyncMock(
                return_value=session_instance
            )
            session_mock.return_value.__aexit__ = AsyncMock(return_value=False)
            result_mock = MagicMock()
            result_mock.scalar_one_or_none = MagicMock(return_value=None)
            session_instance.execute = AsyncMock(return_value=result_mock)

            result = await _send_confirmation_request(1, 200)
            assert result is True
            notify.assert_awaited_once()

    async def test_skips_when_already_accepted(self):
        meeting = make_meeting(
            id=1,
            participants=[_creator(), _other(200)],
            mentor_telegram_id=CREATOR_ID,
            proposal_status=ProposalStatus.pending_confirmation,
            proposed_by=CREATOR_ID,
        )

        with (
            patch("src.tasks.meeting._load_meeting", AsyncMock(return_value=meeting)),
            patch(
                "src.tasks.meeting._send_meeting_notification",
                AsyncMock(return_value=True),
            ) as notify,
            patch(
                "src.core.database.async_session_maker",
                MagicMock(),
            ) as session_mock,
            patch(
                "src.dao.user.UserDAO.find_one_or_none",
                AsyncMock(return_value=_creator()),
            ),
        ):
            session_instance = AsyncMock()
            session_mock.return_value.__aenter__ = AsyncMock(
                return_value=session_instance
            )
            session_mock.return_value.__aexit__ = AsyncMock(return_value=False)
            result_mock = MagicMock()
            result_mock.scalar_one_or_none = MagicMock(return_value=True)
            session_instance.execute = AsyncMock(return_value=result_mock)

            result = await _send_confirmation_request(1, 200)
            assert result is False
            notify.assert_not_awaited()


class TestSendFinalReminders:
    async def test_sends_to_all_registered_participants(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        meeting = make_meeting(
            id=1,
            participants=[_creator(), _other(200)],
            mentor_telegram_id=CREATOR_ID,
            scheduled_at=future,
        )

        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch(
                "src.core.database.async_session_maker",
                MagicMock(),
            ) as session_mock,
            patch("src.tasks.meeting.get_worker_bot", MagicMock()),
            patch(
                "src.tasks.meeting._send_meeting_notification",
                AsyncMock(return_value=True),
            ) as notify,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()

            session_instance = AsyncMock()
            session_mock.return_value.__aenter__ = AsyncMock(
                return_value=session_instance
            )
            session_mock.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock scalar_one_or_none to return a future meeting
            result_mock = MagicMock()
            result_mock.unique = MagicMock(return_value=result_mock)
            result_mock.scalars = MagicMock(return_value=result_mock)
            result_mock.all = MagicMock(return_value=[meeting])
            session_instance.execute = AsyncMock(return_value=result_mock)

            await _send_final_reminders_async()

            assert notify.await_count == 2  # creator + other


class TestRequestDueCallDurations:
    async def test_missing_template_returns(self):
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.dao.survey_template.SurveyTemplateDAO") as mock_template_dao,
            patch("src.tasks.meeting.MeetingDAO") as mock_meeting_dao,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_template_dao.get_by_slug = AsyncMock(return_value=None)
            mock_meeting_dao.find_due_call_duration_request_meetings = AsyncMock()

            await _request_due_call_durations_async()

            mock_template_dao.get_by_slug.assert_awaited_once_with(
                "call_duration_actual"
            )
            mock_meeting_dao.find_due_call_duration_request_meetings.assert_not_called()

    async def test_no_due_meetings(self):
        template = SimpleNamespace(id=10)
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.dao.survey_template.SurveyTemplateDAO") as mock_template_dao,
            patch("src.tasks.meeting.MeetingDAO") as mock_meeting_dao,
            patch("src.services.survey_session.SurveySessionService") as mock_service,
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_template_dao.get_by_slug = AsyncMock(return_value=template)
            mock_meeting_dao.find_due_call_duration_request_meetings = AsyncMock(
                return_value=[]
            )

            await _request_due_call_durations_async()

            mock_service.assert_not_called()

    async def test_due_meeting_creates_session_and_sends_initial_message(self):
        template = SimpleNamespace(id=10)
        meeting = make_meeting(id=42, mentor_telegram_id=CREATOR_ID)
        survey_session = SimpleNamespace(id=77)
        bot = AsyncMock()
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.dao.survey_template.SurveyTemplateDAO") as mock_template_dao,
            patch("src.tasks.meeting.MeetingDAO") as mock_meeting_dao,
            patch("src.services.survey_session.SurveySessionService") as mock_service,
            patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
            patch("src.tasks.meeting.get_worker_bot", return_value=bot),
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_template_dao.get_by_slug = AsyncMock(return_value=template)
            mock_meeting_dao.find_due_call_duration_request_meetings = AsyncMock(
                return_value=[meeting]
            )
            mock_service.return_value.create_session = AsyncMock(
                return_value=(survey_session, False)
            )
            mock_session_dao.update_escalation_field = AsyncMock()

            await _request_due_call_durations_async()

            mock_service.return_value.create_session.assert_awaited_once_with(
                template_id=10,
                respondent_id=CREATOR_ID,
                context_type="call_duration",
                context_id="42",
            )
            mock_session_dao.update_escalation_field.assert_awaited_once_with(
                77, "is_escalatable", False
            )
            bot.send_message.assert_awaited_once()
            assert bot.send_message.await_args.args[0] == CREATOR_ID

    async def test_existing_session_skips_initial_message(self):
        template = SimpleNamespace(id=10)
        meeting = make_meeting(id=42, mentor_telegram_id=CREATOR_ID)
        survey_session = SimpleNamespace(id=77)
        bot = AsyncMock()
        with (
            patch("src.tasks.meeting.celery_db") as mock_db,
            patch("src.dao.survey_template.SurveyTemplateDAO") as mock_template_dao,
            patch("src.tasks.meeting.MeetingDAO") as mock_meeting_dao,
            patch("src.services.survey_session.SurveySessionService") as mock_service,
            patch("src.dao.survey_session.SurveySessionDAO") as mock_session_dao,
            patch("src.tasks.meeting.get_worker_bot", return_value=bot),
        ):
            mock_db.return_value.__aenter__ = AsyncMock()
            mock_db.return_value.__aexit__ = AsyncMock()
            mock_template_dao.get_by_slug = AsyncMock(return_value=template)
            mock_meeting_dao.find_due_call_duration_request_meetings = AsyncMock(
                return_value=[meeting]
            )
            mock_service.return_value.create_session = AsyncMock(
                return_value=(survey_session, True)
            )
            mock_session_dao.update_escalation_field = AsyncMock()

            await _request_due_call_durations_async()

            bot.send_message.assert_not_called()
            mock_session_dao.update_escalation_field.assert_not_called()
