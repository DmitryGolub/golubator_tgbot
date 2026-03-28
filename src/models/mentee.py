from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.mentor import Mentor
    from src.models.user import User


class Mentee(Base):
    __tablename__ = "mentees"
    __table_args__ = {"schema": "iam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        unique=True,
        index=True,
    )
    notion_page_id: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, index=True, nullable=True
    )
    doc_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mentor_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("iam.mentors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contract: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false()
    )
    intern: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contract_version: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contract_expires: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    student_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="mentee_profile",
        foreign_keys=[telegram_id],
        lazy="selectin",
    )
    mentor: Mapped[Optional["Mentor"]] = relationship(
        "Mentor",
        foreign_keys=[mentor_id],
        lazy="selectin",
    )
