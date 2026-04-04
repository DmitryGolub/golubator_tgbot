from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Cohort(Base):
    __tablename__ = "cohorts"
    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_cohort_type_value"),
        {"schema": "integrations"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)


class UserCohort(Base):
    __tablename__ = "user_cohorts"
    __table_args__ = (
        Index("ix_user_cohorts_cohort_id", "cohort_id"),
        {"schema": "integrations"},
    )

    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    cohort_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("integrations.cohorts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cohort: Mapped["Cohort"] = relationship("Cohort", lazy="selectin")
