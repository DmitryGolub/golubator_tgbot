from pydantic import BaseModel


class MentorStatsResponse(BaseModel):
    mentor_id: int
    total_calls: int
    total_surveys: int
    avg_mentor_style: float | None
    avg_knowledge_depth: float | None
    avg_understanding: float | None
    avg_satisfaction: float | None
