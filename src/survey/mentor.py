from typing import Optional

from pydantic import BaseModel, Field


class MentorStatsResponse(BaseModel):
    mentor_id: int
    total_calls: int = Field(description="Количество завершённых созвонов")
    total_surveys: int = Field(description="Количество заполненных анкет")
    avg_mentor_style: Optional[float] = Field(
        None, description="Средний стиль общения ментора (1-5)"
    )
    avg_knowledge_depth: Optional[float] = Field(
        None, description="Средняя глубина проверки знаний (1-5)"
    )
    avg_understanding: Optional[float] = Field(
        None, description="Среднее понимание материала (1-5)"
    )
    avg_satisfaction: Optional[float] = Field(
        None,
        description="Средняя общая оценка (среднее всех трёх метрик)",
    )
