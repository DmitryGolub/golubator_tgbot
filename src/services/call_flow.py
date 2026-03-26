import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from src.dao.meeting import MeetingDAO
from src.models.meeting import Meeting
from src.models.user import User
from src.utils.roles import is_mentor, is_student

logger = logging.getLogger(__name__)


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
    def __init__(self, meeting: Meeting):
        super().__init__("Active call already exists")
        self.meeting = meeting


class CallAlreadyExistsError(CallFlowError):
    def __init__(self, meeting: Meeting):
        super().__init__("Call for this meeting already exists")
        self.meeting = meeting


@dataclass(slots=True)
class EndCallResult:
    meeting: Meeting
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

    mentor = next(
        (participant for participant in meeting.participants if is_mentor(participant)),
        None,
    )
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
    ) -> Meeting:
        meeting = await MeetingDAO.get_with_participants(meeting_id)
        if not meeting:
            raise MeetingNotFoundError

        mentor = _resolve_mentor(meeting, mentor_id)
        if not mentor:
            raise MentorNotInMeetingError

        if meeting.completed_at is not None:
            raise MeetingAlreadyCompletedError

        active = await MeetingDAO.get_active_call_for_mentor(mentor_id)
        if active:
            raise ActiveCallAlreadyExistsError(active)

        if meeting.call_status is not None:
            raise CallAlreadyExistsError(meeting)

        student = _resolve_student(meeting)
        if not student:
            raise MeetingStudentNotFoundError

        try:
            started = await MeetingDAO.start_call(meeting_id, student.telegram_id)
        except IntegrityError:
            # Concurrent call creation — re-check state
            existing = await MeetingDAO.get_active_call_for_mentor(mentor_id)
            if existing:
                raise ActiveCallAlreadyExistsError(existing)
            refreshed = await MeetingDAO.get_with_participants(meeting_id)
            if refreshed and refreshed.call_status is not None:
                raise CallAlreadyExistsError(refreshed)
            raise

        if not started:
            raise CallAlreadyExistsError(meeting)

        logger.info(
            "Call started: meeting=%s mentor=%s student=%s",
            meeting_id,
            mentor_id,
            student.telegram_id,
        )
        return started

    async def end_active_call(self, *, mentor_id: int) -> EndCallResult:
        active_meeting = await MeetingDAO.get_active_call_for_mentor(mentor_id)
        if not active_meeting:
            raise ActiveCallNotFoundError

        finished_meeting = await MeetingDAO.finish_call(active_meeting.id, mentor_id)
        if not finished_meeting:
            raise ActiveCallNotFoundError

        meeting_was_completed = finished_meeting.completed_at is not None

        result = EndCallResult(
            meeting=finished_meeting,
            meeting_was_completed=meeting_was_completed,
        )
        logger.info(
            "Call ended: meeting=%s mentor=%s meeting_completed=%s",
            finished_meeting.id,
            mentor_id,
            meeting_was_completed,
        )

        # Emit call_ended trigger for dynamic actions (surveys, notifications)
        if meeting_was_completed:
            try:
                from src.models.trigger import TriggerType
                from src.services.events.dispatcher import EventDispatcher

                await EventDispatcher.emit(
                    TriggerType.call_ended,
                    {
                        "meeting_id": finished_meeting.id,
                        "mentor_id": finished_meeting.mentor_telegram_id,
                        "student_id": finished_meeting.student_telegram_id,
                    },
                )
            except Exception:
                # Trigger failure is non-fatal: call was already ended successfully
                logger.exception("Failed to emit call_ended event")

        return result
