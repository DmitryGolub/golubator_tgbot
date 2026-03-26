from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.user import User


class Mentor(Base):
    __tablename__ = "mentors"
    __table_args__ = {"schema": "iam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    notion_page_id: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, index=True, nullable=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    about: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    membership_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
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
        back_populates="mentor_profile",
        foreign_keys=[telegram_id],
        lazy="selectin",
    )
