from typing import Optional

from pydantic import BaseModel

from src.survey.schemas import SurveyAnswer, SurveyQuestion, SurveyStatus


class SurveyStateResponse(BaseModel):
    status: SurveyStatus
    response: Optional[SurveyAnswer] = None
    questions: list[SurveyQuestion] | None = None


class SurveySubmitResponse(BaseModel):
    already_submitted: bool
    response: SurveyAnswer
