from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.mentor_feedback.constants import (
    MENTOR_FEEDBACK_DURATION_SQL,
    MENTOR_FEEDBACK_STATUS_SQL,
)


class MentorFeedback(Base):
    __tablename__ = "mentor_feedback"
    __table_args__ = (
        Index("ix_mentor_feedback_call_id", "call_id", unique=True),
        CheckConstraint(
            f"status IN ({MENTOR_FEEDBACK_STATUS_SQL})",
            name="ck_mentor_feedback_status",
        ),
        CheckConstraint(
            f"duration IN ({MENTOR_FEEDBACK_DURATION_SQL})",
            name="ck_mentor_feedback_duration",
        ),
        CheckConstraint(
            "motivation BETWEEN 1 AND 5",
            name="ck_mentor_feedback_motivation_range",
        ),
        CheckConstraint(
            "neuromutation_stage BETWEEN 1 AND 10",
            name="ck_mentor_feedback_neuromutation_stage_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    mentor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration: Mapped[str] = mapped_column(String(32), nullable=False)
    motivation: Mapped[int] = mapped_column(Integer, nullable=False)
    neuromutation_stage: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    meeting: Mapped["Meeting"] = relationship("Meeting", lazy="selectin")
    mentor: Mapped["User"] = relationship("User", lazy="selectin")
