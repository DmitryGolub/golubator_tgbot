from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.services.call_flow import (
    ActiveCallAlreadyExistsError,
    ActiveCallNotFoundError,
    CallAlreadyExistsError,
    CallFlowService,
    MeetingAlreadyCompletedError,
    MeetingNotFoundError,
    MentorNotInMeetingError,
    NoOtherParticipantsError,
    _is_participant,
    _resolve_mentor,
    _resolve_other_participants,
    _resolve_student,
)
from tests.conftest import make_meeting, make_user

MENTOR_ID = 100
STUDENT_ID = 200
MEETING_ID = 1


def _mentor():
    return make_user(telegram_id=MENTOR_ID)


def _student():
    return make_user(telegram_id=STUDENT_ID)


def _meeting(**kwargs):
    defaults = dict(
        id=MEETING_ID,
        participants=[_mentor(), _student()],
        mentor_telegram_id=MENTOR_ID,
    )
    defaults.update(kwargs)
    return make_meeting(**defaults)


class TestIsParticipant:
    def test_is_participant(self):
        meeting = _meeting()
        assert _is_participant(meeting, MENTOR_ID) is True
        assert _is_participant(meeting, STUDENT_ID) is True

    def test_not_participant(self):
        meeting = _meeting()
        assert _is_participant(meeting, 999) is False


class TestResolveMentor:
    def test_found(self):
        meeting = _meeting()
        assert _resolve_mentor(meeting, MENTOR_ID) is not None

    def test_not_in_participants(self):
        meeting = _meeting()
        assert _resolve_mentor(meeting, 999) is None


class TestResolveOtherParticipants:
    def test_single_other(self):
        meeting = _meeting()
        result = _resolve_other_participants(meeting, MENTOR_ID)
        assert len(result) == 1
        assert result[0].telegram_id == STUDENT_ID

    def test_multiple_participants(self):
        p3 = make_user(telegram_id=300)
        meeting = _meeting(participants=[_mentor(), _student(), p3])
        result = _resolve_other_participants(meeting, MENTOR_ID)
        assert len(result) == 2
        assert {p.telegram_id for p in result} == {STUDENT_ID, 300}

    def test_empty_participants(self):
        meeting = make_meeting(participants=[])
        result = _resolve_other_participants(meeting, MENTOR_ID)
        assert result == []


class TestResolveStudent:
    def test_found_by_student_telegram_id(self):
        meeting = _meeting(student_telegram_id=STUDENT_ID)
        result = _resolve_student(meeting)
        assert result is not None
        assert result.telegram_id == STUDENT_ID

    def test_fallback_non_mentor(self):
        other = make_user(telegram_id=300)
        meeting = make_meeting(
            participants=[_mentor(), other],
            mentor_telegram_id=MENTOR_ID,
        )
        result = _resolve_student(meeting)
        assert result is not None
        assert result.telegram_id == 300

    def test_empty_participants(self):
        meeting = make_meeting(participants=[])
        assert _resolve_student(meeting) is None


@patch("src.services.call_flow.MeetingDAO")
class TestStartCall:
    async def test_happy_path(self, mock_meeting_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=_meeting())
        mock_meeting_dao.get_active_call_for_user = AsyncMock(return_value=None)
        started = _meeting(call_status="ongoing", student_telegram_id=STUDENT_ID)
        mock_meeting_dao.start_call = AsyncMock(return_value=started)

        result = await CallFlowService().start_call(
            mentor_id=MENTOR_ID, meeting_id=MEETING_ID
        )
        assert result.id == started.id
        mock_meeting_dao.start_call.assert_awaited_once_with(MEETING_ID)

    async def test_meeting_not_found(self, mock_meeting_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=None)
        with pytest.raises(MeetingNotFoundError):
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )

    async def test_user_not_participant(self, mock_meeting_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=_meeting())
        with pytest.raises(MentorNotInMeetingError):
            await CallFlowService().start_call(mentor_id=999, meeting_id=MEETING_ID)

    async def test_meeting_already_completed(self, mock_meeting_dao):
        meeting = _meeting(completed_at=datetime.now(timezone.utc))
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=meeting)
        with pytest.raises(MeetingAlreadyCompletedError):
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )

    async def test_active_call_exists(self, mock_meeting_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=_meeting())
        existing = _meeting(call_status="ongoing", student_telegram_id=STUDENT_ID)
        mock_meeting_dao.get_active_call_for_user = AsyncMock(return_value=existing)
        with pytest.raises(ActiveCallAlreadyExistsError) as exc_info:
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )
        assert exc_info.value.meeting is existing

    async def test_call_for_meeting_exists(self, mock_meeting_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(
            return_value=_meeting(call_status="finished")
        )
        mock_meeting_dao.get_active_call_for_user = AsyncMock(return_value=None)
        with pytest.raises(CallAlreadyExistsError):
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )

    async def test_no_other_participants(self, mock_meeting_dao):
        meeting = make_meeting(
            participants=[_mentor()],
            mentor_telegram_id=MENTOR_ID,
        )
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=meeting)
        mock_meeting_dao.get_active_call_for_user = AsyncMock(return_value=None)
        with pytest.raises(NoOtherParticipantsError):
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )


@patch("src.services.call_flow.MeetingDAO")
class TestEndActiveCall:
    async def test_happy_path(self, mock_meeting_dao):
        started_at = datetime.now(timezone.utc) - timedelta(minutes=45)
        active = _meeting(
            call_status="ongoing",
            call_started_at=started_at,
            mentor_telegram_id=MENTOR_ID,
            student_telegram_id=STUDENT_ID,
        )
        finished = _meeting(
            call_status="finished",
            call_started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            mentor_telegram_id=MENTOR_ID,
            student_telegram_id=STUDENT_ID,
        )
        mock_meeting_dao.get_active_call_for_user = AsyncMock(return_value=active)
        mock_meeting_dao.finish_call = AsyncMock(return_value=finished)

        result = await CallFlowService().end_active_call(mentor_id=MENTOR_ID)
        assert result.meeting is finished
        assert result.meeting_was_completed is True

    async def test_no_active_call(self, mock_meeting_dao):
        mock_meeting_dao.get_active_call_for_user = AsyncMock(return_value=None)
        with pytest.raises(ActiveCallNotFoundError):
            await CallFlowService().end_active_call(mentor_id=MENTOR_ID)

    async def test_happy_path_has_duration(self, mock_meeting_dao):
        started_at = datetime.now(timezone.utc) - timedelta(minutes=45)
        active = _meeting(
            call_status="ongoing",
            call_started_at=started_at,
            mentor_telegram_id=MENTOR_ID,
            student_telegram_id=STUDENT_ID,
        )
        finished = _meeting(
            call_status="finished",
            call_started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            mentor_telegram_id=MENTOR_ID,
            student_telegram_id=STUDENT_ID,
        )
        mock_meeting_dao.get_active_call_for_user = AsyncMock(return_value=active)
        mock_meeting_dao.finish_call = AsyncMock(return_value=finished)

        result = await CallFlowService().end_active_call(mentor_id=MENTOR_ID)
        assert result.meeting.call_duration_minutes == 45

    async def test_finish_returns_none(self, mock_meeting_dao):
        active = _meeting(call_status="ongoing")
        mock_meeting_dao.get_active_call_for_user = AsyncMock(return_value=active)
        mock_meeting_dao.finish_call = AsyncMock(return_value=None)
        with pytest.raises(ActiveCallNotFoundError):
            await CallFlowService().end_active_call(mentor_id=MENTOR_ID)


class TestCallDuration:
    def test_duration_with_both_timestamps(self):
        started = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
        ended = datetime(2026, 4, 5, 11, 30, tzinfo=timezone.utc)
        meeting = make_meeting(call_started_at=started, completed_at=ended)
        assert meeting.call_duration == timedelta(hours=1, minutes=30)
        assert meeting.call_duration_minutes == 90

    def test_duration_without_completed_at(self):
        started = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
        meeting = make_meeting(call_started_at=started)
        assert meeting.call_duration is None
        assert meeting.call_duration_minutes is None

    def test_duration_without_started_at(self):
        ended = datetime(2026, 4, 5, 11, 0, tzinfo=timezone.utc)
        meeting = make_meeting(completed_at=ended)
        assert meeting.call_duration is None
        assert meeting.call_duration_minutes is None

    def test_duration_short_call(self):
        started = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
        ended = started + timedelta(minutes=7, seconds=29)
        meeting = make_meeting(call_started_at=started, completed_at=ended)
        assert meeting.call_duration_minutes == 7

    def test_duration_rounding(self):
        started = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
        ended = started + timedelta(minutes=30, seconds=31)
        meeting = make_meeting(call_started_at=started, completed_at=ended)
        assert meeting.call_duration_minutes == 31
