import logging

from src.dao.survey_session import SurveySessionDAO
from src.dao.survey_template import SurveyTemplateDAO
from src.models.survey_session import SessionStatus, SurveySession
from src.models.survey_template import QuestionType, SurveyQuestion

logger = logging.getLogger(__name__)

CALL_DURATION_TEMPLATE_SLUG = "call_duration_actual"
CALL_DURATION_CONTEXT_TYPE = "call_duration"


class SessionNotFoundError(Exception):
    pass


class SessionAlreadyCompletedError(Exception):
    pass


class SessionNotOwnedError(Exception):
    pass


class TemplateNotFoundError(Exception):
    pass


class SurveySessionService:
    async def create_session(
        self,
        *,
        template_id: int,
        respondent_id: int,
        context_type: str | None = None,
        context_id: str | None = None,
    ) -> tuple[SurveySession, bool]:
        """Create or find existing session. Returns (session, already_existed)."""
        template = await SurveyTemplateDAO.get_by_id(template_id)
        if not template:
            raise TemplateNotFoundError

        return await SurveySessionDAO.create(
            template_id=template_id,
            respondent_id=respondent_id,
            context_type=context_type,
            context_id=context_id,
        )

    async def create_session_by_slug(
        self,
        *,
        slug: str,
        respondent_id: int,
        context_type: str | None = None,
        context_id: str | None = None,
    ) -> tuple[SurveySession, bool]:
        template = await SurveyTemplateDAO.get_by_slug(slug)
        if not template:
            raise TemplateNotFoundError

        return await SurveySessionDAO.create(
            template_id=template.id,
            respondent_id=respondent_id,
            context_type=context_type,
            context_id=context_id,
        )

    async def get_available_sessions(self, respondent_id: int) -> list[SurveySession]:
        return await SurveySessionDAO.get_pending_for_respondent(respondent_id)

    async def get_session(self, session_id: int) -> SurveySession:
        session = await SurveySessionDAO.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError
        return session

    async def start_session(self, session_id: int, caller_id: int) -> SurveySession:
        session = await SurveySessionDAO.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError
        if session.respondent_id != caller_id:
            raise SessionNotOwnedError
        if session.status == SessionStatus.completed:
            raise SessionAlreadyCompletedError

        if session.status == SessionStatus.pending:
            session = await SurveySessionDAO.start(session_id)

        return session

    async def get_questions(self, session_id: int) -> list[SurveyQuestion]:
        session = await SurveySessionDAO.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError

        template = await SurveyTemplateDAO.get_by_id(session.template_id)
        if not template:
            raise TemplateNotFoundError

        return list(template.questions)

    async def save_answer(
        self,
        *,
        session_id: int,
        question: SurveyQuestion,
        raw_value: str,
    ) -> None:
        value_text = None
        value_int = None
        value_choice = None

        if question.question_type == QuestionType.text:
            value_text = raw_value
        elif question.question_type == QuestionType.rating:
            try:
                value_int = int(raw_value)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid rating value: {raw_value}")
        elif question.question_type == QuestionType.single_choice:
            value_choice = [raw_value]
        elif question.question_type == QuestionType.multiple_choice:
            value_choice = (
                raw_value.split(",") if isinstance(raw_value, str) else raw_value
            )

        await SurveySessionDAO.save_answer(
            session_id=session_id,
            question_id=question.id,
            value_text=value_text,
            value_int=value_int,
            value_choice=value_choice,
        )

    async def complete_session(self, session_id: int) -> SurveySession:
        session = await SurveySessionDAO.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError
        if session.status == SessionStatus.completed:
            raise SessionAlreadyCompletedError

        session = await SurveySessionDAO.complete(session_id)

        # Reload with answers for analytics / completion hooks
        session = await SurveySessionDAO.get_by_id(session_id)
        if session:
            if await self._complete_call_duration_session(session):
                return session

            from src.services.survey_analytics import SurveyAnalytics

            try:
                await SurveyAnalytics().process_completed_session(session)
            except Exception:
                logger.exception("SurveyAnalytics failed for session %d", session_id)

        return session

    async def _complete_call_duration_session(self, session: SurveySession) -> bool:
        if not session.template:
            return False
        if session.template.slug != CALL_DURATION_TEMPLATE_SLUG:
            return False
        if session.context_type != CALL_DURATION_CONTEXT_TYPE or not session.context_id:
            return False

        try:
            meeting_id = int(session.context_id)
            answer = session.answers[0] if session.answers else None
            minutes = int(answer.value_text) if answer and answer.value_text else None
        except (TypeError, ValueError):
            logger.warning(
                "Invalid call duration survey answer: session=%s context_id=%s",
                session.id,
                session.context_id,
            )
            return True

        if minutes is None:
            logger.warning(
                "Missing call duration survey answer: session=%s", session.id
            )
            return True

        from src.services.call_flow import CallFlowService

        await CallFlowService().end_call_with_actual_duration(
            meeting_id=meeting_id,
            user_id=session.respondent_id,
            actual_duration_minutes=minutes,
        )
        return True
