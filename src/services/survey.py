from src.dao.survey_template import SurveyTemplateDAO


class CallNotFoundError(Exception):
    pass


class SurveyNotAvailableError(Exception):
    pass


class SurveyService:
    """Legacy-compatible survey service.

    Provides backward-compatible API endpoints while using the new
    SurveyTemplate/SurveySession infrastructure underneath.
    """

    async def get_template_questions(self, slug: str = "post_call_student"):
        template = await SurveyTemplateDAO.get_by_slug(slug)
        if not template:
            return []
        return template.questions
