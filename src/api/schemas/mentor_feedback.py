from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.mentor_feedback.constants import (
    MentorFeedbackDuration,
    MentorFeedbackStatus,
)


class MentorFeedbackCreateRequest(BaseModel):
    mentor_id: int = Field(gt=0)
    status: MentorFeedbackStatus
    duration: MentorFeedbackDuration
    motivation: int = Field(ge=1, le=5)
    neuromutation_stage: int = Field(ge=1, le=10)
    comment: Optional[str] = None


class MentorFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: int
    mentor_id: int
    status: MentorFeedbackStatus
    duration: MentorFeedbackDuration
    motivation: int
    neuromutation_stage: int
    comment: Optional[str]
    created_at: datetime
