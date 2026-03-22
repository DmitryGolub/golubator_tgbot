from sqlalchemy.exc import IntegrityError

from src.dao.meeting import MeetingDAO
from src.dao.mentor_feedback import MentorFeedbackDAO
from src.mentor_feedback.errors import (
    CallNotFoundError,
    MentorFeedbackAlreadyExistsError,
    MentorNotInCallError,
)
from src.mentor_feedback.dto import MentorFeedbackCreateData
from src.models.mentor_feedback import MentorFeedback
from src.utils.roles import is_mentor


class MentorFeedbackService:
    async def create_feedback(
        self,
        *,
        call_id: int,
        mentor_id: int,
        payload: MentorFeedbackCreateData,
    ) -> MentorFeedback:
        meeting = await MeetingDAO.get_with_participants(call_id)
        if not meeting:
            raise CallNotFoundError

        mentor = next(
            (
                participant
                for participant in meeting.participants
                if participant.telegram_id == mentor_id and is_mentor(participant)
            ),
            None,
        )
        if not mentor:
            raise MentorNotInCallError

        existing_feedback = await MentorFeedbackDAO.get_by_call_id(call_id)
        if existing_feedback:
            raise MentorFeedbackAlreadyExistsError

        try:
            return await MentorFeedbackDAO.create(
                call_id=call_id,
                mentor_id=mentor_id,
                status=payload.status.value,
                duration=payload.duration.value,
                motivation=payload.motivation,
                neuromutation_stage=payload.neuromutation_stage,
                comment=payload.comment,
            )
        except IntegrityError as exc:
            existing_feedback = await MentorFeedbackDAO.get_by_call_id(call_id)
            if existing_feedback:
                raise MentorFeedbackAlreadyExistsError from exc
            raise
