from typing import Optional

from pydantic import BaseModel


class SurveyTemplateResponse(BaseModel):
    id: int
    title: str
    slug: str
    description: Optional[str] = None
    questions_count: int


class SurveySessionResponse(BaseModel):
    id: int
    template_id: int
    respondent_id: int
    context_type: Optional[str] = None
    context_id: Optional[str] = None
    status: str
