from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    __table_args__ = (
        UniqueConstraint("call_id", name="uq_survey_response_call_id"),
        CheckConstraint(
            "mentor_style BETWEEN 1 AND 5",
            name="ck_survey_response_mentor_style_range",
        ),
        CheckConstraint(
            "knowledge_depth BETWEEN 1 AND 5",
            name="ck_survey_response_knowledge_depth_range",
        ),
        CheckConstraint(
            "understanding BETWEEN 1 AND 5",
            name="ck_survey_response_understanding_range",
        ),
        CheckConstraint(
            "duration_option IN ('lt_30', '30_45', '45_60', 'gt_60')",
            name="ck_survey_response_duration_option",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    duration_option: Mapped[str] = mapped_column(String(32), nullable=False)
    mentor_style: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    understanding: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        back_populates="survey_response",
        lazy="selectin",
    )
    student: Mapped["User"] = relationship(
        "User",
        back_populates="survey_responses",
        lazy="selectin",
    )
