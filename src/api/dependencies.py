from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from src.services.mentor_feedback import MentorFeedbackService


async def get_mentor_feedback_service() -> "MentorFeedbackService":
    from src.services.mentor_feedback import MentorFeedbackService

    return MentorFeedbackService()
