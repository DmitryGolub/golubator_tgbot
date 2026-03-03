from src.services.mentor_feedback import MentorFeedbackService


async def get_mentor_feedback_service() -> MentorFeedbackService:
    return MentorFeedbackService()
