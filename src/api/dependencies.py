from src.services.survey import SurveyService


async def get_survey_service() -> SurveyService:
    return SurveyService()
