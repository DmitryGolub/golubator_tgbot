from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.survey_session import (
    SessionAlreadyCompletedError,
    SessionNotFoundError,
    SurveySessionService,
    TemplateNotFoundError,
)


def _template(id=1, slug="test"):
    return SimpleNamespace(id=id, slug=slug, questions=[])


def _session(id=1, status="pending", template_id=1):
    return SimpleNamespace(
        id=id,
        status=SimpleNamespace(value=status),
        template_id=template_id,
    )


def _question(id=1, question_type="text"):
    return SimpleNamespace(id=id, question_type=question_type)


# Patch SessionStatus enum from the module
@pytest.fixture(autouse=True)
def _patch_session_status():
    """Make SimpleNamespace status comparable with SessionStatus enum."""


@patch("src.services.survey_session.SurveySessionDAO")
@patch("src.services.survey_session.SurveyTemplateDAO")
class TestCreateSession:
    async def test_template_not_found(self, mock_tmpl_dao, mock_sess_dao):
        mock_tmpl_dao.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(TemplateNotFoundError):
            await SurveySessionService().create_session(
                template_id=1, respondent_id=100
            )

    async def test_success(self, mock_tmpl_dao, mock_sess_dao):
        mock_tmpl_dao.get_by_id = AsyncMock(return_value=_template())
        session = _session()
        mock_sess_dao.create = AsyncMock(return_value=(session, False))
        result = await SurveySessionService().create_session(
            template_id=1, respondent_id=100
        )
        assert result == (session, False)

    async def test_by_slug_not_found(self, mock_tmpl_dao, mock_sess_dao):
        mock_tmpl_dao.get_by_slug = AsyncMock(return_value=None)
        with pytest.raises(TemplateNotFoundError):
            await SurveySessionService().create_session_by_slug(
                slug="missing", respondent_id=100
            )


@patch("src.services.survey_session.SurveySessionDAO")
@patch("src.services.survey_session.SurveyTemplateDAO")
class TestStartSession:
    async def test_not_found(self, mock_tmpl_dao, mock_sess_dao):
        mock_sess_dao.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(SessionNotFoundError):
            await SurveySessionService().start_session(1, caller_id=42)

    async def test_wrong_caller(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_session import SessionStatus

        session = SimpleNamespace(
            id=1, status=SessionStatus.pending, respondent_id=99, template_id=1
        )
        mock_sess_dao.get_by_id = AsyncMock(return_value=session)
        with pytest.raises(SessionNotFoundError):
            await SurveySessionService().start_session(1, caller_id=42)

    async def test_already_completed(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_session import SessionStatus

        session = SimpleNamespace(
            id=1, status=SessionStatus.completed, respondent_id=42, template_id=1
        )
        mock_sess_dao.get_by_id = AsyncMock(return_value=session)
        with pytest.raises(SessionAlreadyCompletedError):
            await SurveySessionService().start_session(1, caller_id=42)

    async def test_pending_starts(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_session import SessionStatus

        session = SimpleNamespace(
            id=1, status=SessionStatus.pending, respondent_id=42, template_id=1
        )
        started = SimpleNamespace(
            id=1, status=SessionStatus.in_progress, respondent_id=42, template_id=1
        )
        mock_sess_dao.get_by_id = AsyncMock(return_value=session)
        mock_sess_dao.start = AsyncMock(return_value=started)
        result = await SurveySessionService().start_session(1, caller_id=42)
        assert result is started

    async def test_in_progress_noop(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_session import SessionStatus

        session = SimpleNamespace(
            id=1, status=SessionStatus.in_progress, respondent_id=42, template_id=1
        )
        mock_sess_dao.get_by_id = AsyncMock(return_value=session)
        result = await SurveySessionService().start_session(1, caller_id=42)
        assert result is session
        mock_sess_dao.start.assert_not_called()


@patch("src.services.survey_session.SurveySessionDAO")
@patch("src.services.survey_session.SurveyTemplateDAO")
class TestSaveAnswer:
    async def test_text(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_template import QuestionType

        q = SimpleNamespace(id=1, question_type=QuestionType.text)
        mock_sess_dao.save_answer = AsyncMock()
        await SurveySessionService().save_answer(
            session_id=1, question=q, raw_value="hello"
        )
        mock_sess_dao.save_answer.assert_called_once_with(
            session_id=1,
            question_id=1,
            value_text="hello",
            value_int=None,
            value_choice=None,
        )

    async def test_rating(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_template import QuestionType

        q = SimpleNamespace(id=1, question_type=QuestionType.rating)
        mock_sess_dao.save_answer = AsyncMock()
        await SurveySessionService().save_answer(
            session_id=1, question=q, raw_value="5"
        )
        mock_sess_dao.save_answer.assert_called_once_with(
            session_id=1,
            question_id=1,
            value_text=None,
            value_int=5,
            value_choice=None,
        )

    async def test_single_choice(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_template import QuestionType

        q = SimpleNamespace(id=1, question_type=QuestionType.single_choice)
        mock_sess_dao.save_answer = AsyncMock()
        await SurveySessionService().save_answer(
            session_id=1, question=q, raw_value="option_a"
        )
        mock_sess_dao.save_answer.assert_called_once_with(
            session_id=1,
            question_id=1,
            value_text=None,
            value_int=None,
            value_choice=["option_a"],
        )

    async def test_multiple_choice(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_template import QuestionType

        q = SimpleNamespace(id=1, question_type=QuestionType.multiple_choice)
        mock_sess_dao.save_answer = AsyncMock()
        await SurveySessionService().save_answer(
            session_id=1, question=q, raw_value="a,b,c"
        )
        mock_sess_dao.save_answer.assert_called_once_with(
            session_id=1,
            question_id=1,
            value_text=None,
            value_int=None,
            value_choice=["a", "b", "c"],
        )


@patch("src.services.survey_session.SurveySessionDAO")
@patch("src.services.survey_session.SurveyTemplateDAO")
class TestCompleteSession:
    async def test_not_found(self, mock_tmpl_dao, mock_sess_dao):
        mock_sess_dao.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(SessionNotFoundError):
            await SurveySessionService().complete_session(1)

    async def test_already_completed(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_session import SessionStatus

        session = SimpleNamespace(id=1, status=SessionStatus.completed, template_id=1)
        mock_sess_dao.get_by_id = AsyncMock(return_value=session)
        with pytest.raises(SessionAlreadyCompletedError):
            await SurveySessionService().complete_session(1)

    async def test_success(self, mock_tmpl_dao, mock_sess_dao):
        from src.models.survey_session import SessionStatus

        session = SimpleNamespace(id=1, status=SessionStatus.in_progress, template_id=1)
        completed = SimpleNamespace(
            id=1,
            status=SessionStatus.completed,
            template_id=1,
            template=None,
            answers=[],
            respondent_id=1,
            context_id=None,
        )
        mock_sess_dao.get_by_id = AsyncMock(side_effect=[session, completed])
        mock_sess_dao.complete = AsyncMock(return_value=completed)
        result = await SurveySessionService().complete_session(1)
        assert result is completed
