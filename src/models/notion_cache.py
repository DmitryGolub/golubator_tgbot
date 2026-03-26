from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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

if TYPE_CHECKING:
    from src.models.mentee import Mentee


class NotionCohortCache(Base):
    __tablename__ = "notion_cohort_cache"
    __table_args__ = (
        UniqueConstraint(
            "mentee_id",
            "cohort_type",
            "cohort_value",
            name="uq_cohort_cache_mentee_type_value",
        ),
        Index("ix_cohort_cache_type_value", "cohort_type", "cohort_value"),
        {"schema": "integrations"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mentee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("iam.mentees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cohort_type: Mapped[str] = mapped_column(String(100), nullable=False)
    cohort_value: Mapped[str] = mapped_column(String(255), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    mentee: Mapped["Mentee"] = relationship(
        "Mentee",
        back_populates="cohort_cache",
    )
