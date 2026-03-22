from dataclasses import dataclass

from src.dao.call import CallDAO
from src.dao.meeting import MeetingDAO
from src.models.call import Call
from src.models.meeting import Meeting
from src.models.user import User
from src.utils.roles import is_mentor, is_student


class CallFlowError(Exception):
    pass


class MeetingNotFoundError(CallFlowError):
    pass


class MentorNotInMeetingError(CallFlowError):
    pass


class MeetingStudentNotFoundError(CallFlowError):
    pass


class MeetingAlreadyCompletedError(CallFlowError):
    pass


class ActiveCallNotFoundError(CallFlowError):
    pass


class ActiveCallAlreadyExistsError(CallFlowError):
    def __init__(self, call: Call):
        super().__init__("Active call already exists")
        self.call = call


class CallAlreadyExistsError(CallFlowError):
    def __init__(self, call: Call):
        super().__init__("Call for this meeting already exists")
        self.call = call


@dataclass(slots=True)
class EndCallResult:
    call: Call
    meeting: Meeting | None
    meeting_was_completed: bool


def _resolve_mentor(meeting: Meeting, mentor_id: int) -> User | None:
    return next(
        (
            participant
            for participant in meeting.participants
            if participant.telegram_id == mentor_id and is_mentor(participant)
        ),
        None,
    )


def _resolve_student(meeting: Meeting) -> User | None:
    student = next(
        (
            participant
            for participant in meeting.participants
            if is_student(participant)
        ),
        None,
    )
    if student:
        return student

    mentor = next((participant for participant in meeting.participants if is_mentor(participant)), None)
    if mentor:
        return next(
            (
                participant
                for participant in meeting.participants
                if participant.telegram_id != mentor.telegram_id
            ),
            None,
        )
    return None


class CallFlowService:
    async def start_call(
        self,
        *,
        mentor_id: int,
        meeting_id: int,
    ) -> Call:
        meeting = await MeetingDAO.get_with_participants(meeting_id)
        if not meeting:
            raise MeetingNotFoundError

        mentor = _resolve_mentor(meeting, mentor_id)
        if not mentor:
            raise MentorNotInMeetingError

        if meeting.completed_at is not None:
            raise MeetingAlreadyCompletedError

        active_call = await CallDAO.get_active_for_mentor(mentor_id)
        if active_call:
            raise ActiveCallAlreadyExistsError(active_call)

        existing_call = await CallDAO.get_by_meeting_id(meeting_id)
        if existing_call:
            raise CallAlreadyExistsError(existing_call)

        student = _resolve_student(meeting)
        if not student:
            raise MeetingStudentNotFoundError

        return await CallDAO.create_for_meeting(
            meeting_id=meeting_id,
            mentor_id=mentor_id,
            student_id=student.telegram_id,
        )

    async def end_active_call(self, *, mentor_id: int) -> EndCallResult:
        active_call = await CallDAO.get_active_for_mentor(mentor_id)
        if not active_call:
            raise ActiveCallNotFoundError

        finished_call = await CallDAO.finish_call(active_call.id, mentor_id)
        if not finished_call:
            raise ActiveCallNotFoundError

        meeting = None
        meeting_was_completed = False
        if finished_call.meeting_id is not None:
            meeting, meeting_was_completed = await MeetingDAO.complete(
                finished_call.meeting_id,
                completed_at=finished_call.ended_at,
            )

        return EndCallResult(
            call=finished_call,
            meeting=meeting,
            meeting_was_completed=meeting_was_completed,
        )
