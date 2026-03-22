from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from src.models.user import User


class NotionCohortCache(Base):
    __tablename__ = "notion_cohort_cache"
    __table_args__ = (
        UniqueConstraint(
            "user_telegram_id",
            "cohort_type",
            "cohort_value",
            name="uq_cohort_cache_user_type_value",
        ),
        Index("ix_cohort_cache_type_value", "cohort_type", "cohort_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
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

    user: Mapped["User"] = relationship(
        "User",
        back_populates="cohort_cache",
    )
