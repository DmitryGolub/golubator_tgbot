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


class MentorSelfReview(Base):
    __tablename__ = "mentor_self_reviews"

    __table_args__ = (
        UniqueConstraint("mentor_id", "period", name="uq_mentor_self_review_mentor_period"),
        CheckConstraint("workload BETWEEN 1 AND 5", name="ck_mentor_self_review_workload_range"),
        CheckConstraint(
            "pigeon_stupidity BETWEEN 1 AND 5",
            name="ck_mentor_self_review_pigeon_stupidity_range",
        ),
        CheckConstraint(
            "avg_neuromutation BETWEEN 1 AND 10",
            name="ck_mentor_self_review_avg_neuromutation_range",
        ),
        CheckConstraint(
            "period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="ck_mentor_self_review_period_format",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mentor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workload: Mapped[int] = mapped_column(Integer, nullable=False)
    pigeon_stupidity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_neuromutation: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    mentor = relationship("User", back_populates="mentor_self_reviews", lazy="selectin")
