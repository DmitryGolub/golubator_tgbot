import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from src.dao.meeting import MeetingDAO
from src.models.meeting import Meeting
from src.models.user import User

logger = logging.getLogger(__name__)


class CallFlowError(Exception):
    pass


class MeetingNotFoundError(CallFlowError):
    pass


class MentorNotInMeetingError(CallFlowError):
    pass


class UserNotInMeetingError(CallFlowError):
    pass


# Keep old name as alias
MeetingStudentNotFoundError = UserNotInMeetingError


class NoOtherParticipantsError(CallFlowError):
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


def _is_participant(meeting: Meeting, user_id: int) -> bool:
    return any(p.telegram_id == user_id for p in meeting.participants)


def _resolve_other_participants(meeting: Meeting, user_id: int) -> list[User]:
    return [p for p in meeting.participants if p.telegram_id != user_id]


# Keep old names for backward compat with tests
def _resolve_mentor(meeting: Meeting, mentor_id: int) -> User | None:
    if not _is_participant(meeting, mentor_id):
        return None
    return next(
        (p for p in meeting.participants if p.telegram_id == mentor_id),
        None,
    )


def _resolve_student(meeting: Meeting) -> User | None:
    if meeting.student_telegram_id:
        return next(
            (
                p
                for p in meeting.participants
                if p.telegram_id == meeting.student_telegram_id
            ),
            None,
        )
    if meeting.mentor_telegram_id:
        return next(
            (
                p
                for p in meeting.participants
                if p.telegram_id != meeting.mentor_telegram_id
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

        if not _is_participant(meeting, mentor_id):
            raise MentorNotInMeetingError

        if meeting.completed_at is not None:
            raise MeetingAlreadyCompletedError

        active = await MeetingDAO.get_active_call_for_user(mentor_id)
        if active:
            raise ActiveCallAlreadyExistsError(active)

        if meeting.call_status is not None:
            raise CallAlreadyExistsError(meeting)

        others = _resolve_other_participants(meeting, mentor_id)
        if not others:
            raise NoOtherParticipantsError

        try:
            started = await MeetingDAO.start_call(meeting_id)
        except IntegrityError:
            existing = await MeetingDAO.get_active_call_for_user(mentor_id)
            if existing:
                raise ActiveCallAlreadyExistsError(existing)
            refreshed = await MeetingDAO.get_with_participants(meeting_id)
            if refreshed and refreshed.call_status is not None:
                raise CallAlreadyExistsError(refreshed)
            raise

        if not started:
            raise CallAlreadyExistsError(meeting)

        logger.info(
            "Call started: meeting=%s user=%s",
            meeting_id,
            mentor_id,
        )
        return started

    async def end_active_call(self, *, mentor_id: int) -> EndCallResult:
        active_meeting = await MeetingDAO.get_active_call_for_user(mentor_id)
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
            "Call ended: meeting=%s user=%s meeting_completed=%s",
            finished_meeting.id,
            mentor_id,
            meeting_was_completed,
        )

        # Emit call_ended trigger for dynamic actions (surveys, notifications)
        if meeting_was_completed:
            try:
                from src.dao.cohort import CohortDAO
                from src.models.trigger import TriggerType
                from src.services.events.dispatcher import EventDispatcher

                student_id = finished_meeting.student_telegram_id
                participant_ids = [p.telegram_id for p in finished_meeting.participants]
                completed_count = await MeetingDAO.count_completed_for_pair(
                    mentor_id, student_id
                )
                is_first_call = completed_count == 1

                student_stage = None
                if is_first_call and student_id:
                    greeting_ids = await CohortDAO.get_telegram_ids_in_cohort(
                        "Status", "greeting"
                    )
                    if student_id in greeting_ids:
                        student_stage = "greeting"

                await EventDispatcher.emit(
                    TriggerType.call_ended,
                    {
                        "meeting_id": finished_meeting.id,
                        "mentor_id": finished_meeting.mentor_telegram_id,
                        "student_id": student_id,
                        "participant_ids": participant_ids,
                        "is_first_call": is_first_call,
                        "student_stage": student_stage,
                    },
                )
            except Exception:
                logger.exception("Failed to emit call_ended event")

        return result
