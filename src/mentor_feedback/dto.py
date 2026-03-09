from dataclasses import dataclass

from src.mentor_feedback.constants import (
    MentorFeedbackDuration,
    MentorFeedbackStatus,
)


@dataclass(frozen=True, slots=True)
class MentorFeedbackCreateData:
    status: MentorFeedbackStatus
    duration: MentorFeedbackDuration
    motivation: int
    neuromutation_stage: int
    comment: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.motivation <= 5:
            raise ValueError("Мотивация должна быть в диапазоне от 1 до 5")
        if not 1 <= self.neuromutation_stage <= 10:
            raise ValueError("Стадия нейромутации должна быть в диапазоне от 1 до 10")
