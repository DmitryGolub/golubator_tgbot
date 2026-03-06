from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.survey.constants import DurationOption


class SurveyStatus(str, Enum):
    not_available = "not_available"
    available = "available"
    completed = "completed"


class SurveyQuestionOption(BaseModel):
    value: str
    label: str


class SurveyQuestion(BaseModel):
    id: str
    title: str
    kind: Literal["choice", "rating", "text"]
    required: bool
    options: Optional[list[SurveyQuestionOption]] = None
    min_value: Optional[int] = None
    max_value: Optional[int] = None


class SurveyAnswer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    call_id: int
    student_id: int
    duration_option: str
    mentor_style: int
    knowledge_depth: int
    understanding: int
    comment: Optional[str]
    created_at: datetime


class SurveyStateResponse(BaseModel):
    call_id: int
    status: SurveyStatus
    questions: list[SurveyQuestion]
    response: Optional[SurveyAnswer] = None


class SurveySubmitRequest(BaseModel):
    duration_option: DurationOption
    mentor_style: int = Field(ge=1, le=5)
    knowledge_depth: int = Field(ge=1, le=5)
    understanding: int = Field(ge=1, le=5)
    comment: Optional[str] = None


class SurveySubmitResponse(BaseModel):
    call_id: int
    already_submitted: bool
    response: SurveyAnswer
