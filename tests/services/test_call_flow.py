from unittest.mock import AsyncMock, patch

import pytest

from src.services.call_flow import (
    ActiveCallAlreadyExistsError,
    ActiveCallNotFoundError,
    CallAlreadyExistsError,
    CallFlowService,
    MeetingAlreadyCompletedError,
    MeetingNotFoundError,
    MeetingStudentNotFoundError,
    MentorNotInMeetingError,
    _resolve_mentor,
    _resolve_student,
)
from tests.conftest import make_call, make_meeting, make_role, make_user

MENTOR_ID = 100
STUDENT_ID = 200
MEETING_ID = 1


def _mentor():
    return make_user(
        telegram_id=MENTOR_ID,
        role_rel=make_role(is_mentor=True),
    )


def _student():
    return make_user(
        telegram_id=STUDENT_ID,
        role_rel=make_role(is_student=True, name="student"),
    )


def _meeting(**kwargs):
    defaults = dict(
        id=MEETING_ID,
        participants=[_mentor(), _student()],
    )
    defaults.update(kwargs)
    return make_meeting(**defaults)


class TestResolveMentor:
    def test_found(self):
        meeting = _meeting()
        assert _resolve_mentor(meeting, MENTOR_ID) is not None

    def test_not_in_participants(self):
        meeting = _meeting()
        assert _resolve_mentor(meeting, 999) is None

    def test_not_mentor_role(self):
        user = make_user(telegram_id=MENTOR_ID, role_rel=make_role(is_mentor=False))
        meeting = make_meeting(participants=[user])
        assert _resolve_mentor(meeting, MENTOR_ID) is None


class TestResolveStudent:
    def test_found_by_role(self):
        meeting = _meeting()
        result = _resolve_student(meeting)
        assert result is not None
        assert result.telegram_id == STUDENT_ID

    def test_fallback_non_mentor(self):
        mentor = _mentor()
        other = make_user(telegram_id=300, role_rel=None)
        meeting = make_meeting(participants=[mentor, other])
        result = _resolve_student(meeting)
        assert result is not None
        assert result.telegram_id == 300

    def test_empty_participants(self):
        meeting = make_meeting(participants=[])
        assert _resolve_student(meeting) is None


@patch("src.services.call_flow.CallDAO")
@patch("src.services.call_flow.MeetingDAO")
class TestStartCall:
    async def test_happy_path(self, mock_meeting_dao, mock_call_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=_meeting())
        mock_call_dao.get_active_for_mentor = AsyncMock(return_value=None)
        mock_call_dao.get_by_meeting_id = AsyncMock(return_value=None)
        call = make_call()
        mock_call_dao.create_for_meeting = AsyncMock(return_value=call)

        result = await CallFlowService().start_call(
            mentor_id=MENTOR_ID, meeting_id=MEETING_ID
        )
        assert result.id == call.id

    async def test_meeting_not_found(self, mock_meeting_dao, mock_call_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=None)
        with pytest.raises(MeetingNotFoundError):
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )

    async def test_mentor_not_in_meeting(self, mock_meeting_dao, mock_call_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=_meeting())
        with pytest.raises(MentorNotInMeetingError):
            await CallFlowService().start_call(mentor_id=999, meeting_id=MEETING_ID)

    async def test_meeting_already_completed(self, mock_meeting_dao, mock_call_dao):
        from datetime import datetime, timezone

        meeting = _meeting(completed_at=datetime.now(timezone.utc))
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=meeting)
        with pytest.raises(MeetingAlreadyCompletedError):
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )

    async def test_active_call_exists(self, mock_meeting_dao, mock_call_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=_meeting())
        existing = make_call()
        mock_call_dao.get_active_for_mentor = AsyncMock(return_value=existing)
        with pytest.raises(ActiveCallAlreadyExistsError) as exc_info:
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )
        assert exc_info.value.call is existing

    async def test_call_for_meeting_exists(self, mock_meeting_dao, mock_call_dao):
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=_meeting())
        mock_call_dao.get_active_for_mentor = AsyncMock(return_value=None)
        existing = make_call()
        mock_call_dao.get_by_meeting_id = AsyncMock(return_value=existing)
        with pytest.raises(CallAlreadyExistsError):
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )

    async def test_no_student(self, mock_meeting_dao, mock_call_dao):
        meeting = make_meeting(participants=[_mentor()])
        mock_meeting_dao.get_with_participants = AsyncMock(return_value=meeting)
        mock_call_dao.get_active_for_mentor = AsyncMock(return_value=None)
        mock_call_dao.get_by_meeting_id = AsyncMock(return_value=None)
        with pytest.raises(MeetingStudentNotFoundError):
            await CallFlowService().start_call(
                mentor_id=MENTOR_ID, meeting_id=MEETING_ID
            )


@patch("src.services.call_flow.CallDAO")
@patch("src.services.call_flow.MeetingDAO")
class TestEndActiveCall:
    async def test_happy_path(self, mock_meeting_dao, mock_call_dao):
        from datetime import datetime, timezone

        finished = make_call(ended_at=datetime.now(timezone.utc), status="finished")
        mock_call_dao.get_active_for_mentor = AsyncMock(return_value=make_call())
        mock_call_dao.finish_call = AsyncMock(return_value=finished)
        meeting = _meeting()
        mock_meeting_dao.complete = AsyncMock(return_value=(meeting, True))

        result = await CallFlowService().end_active_call(mentor_id=MENTOR_ID)
        assert result.call is finished
        assert result.meeting_was_completed is True

    async def test_no_active_call(self, mock_meeting_dao, mock_call_dao):
        mock_call_dao.get_active_for_mentor = AsyncMock(return_value=None)
        with pytest.raises(ActiveCallNotFoundError):
            await CallFlowService().end_active_call(mentor_id=MENTOR_ID)

    async def test_finish_returns_none(self, mock_meeting_dao, mock_call_dao):
        mock_call_dao.get_active_for_mentor = AsyncMock(return_value=make_call())
        mock_call_dao.finish_call = AsyncMock(return_value=None)
        with pytest.raises(ActiveCallNotFoundError):
            await CallFlowService().end_active_call(mentor_id=MENTOR_ID)
