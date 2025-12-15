import enum
from typing import Optional
from datetime import datetime
from sqlalchemy import Integer, Text, DateTime, ForeignKey, Enum, func, BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.user import State, User
from src.core.database import Base


class Regularity(enum.Enum):
    day = "day"
    week = "week"
    fortnight = "fortnight"
    month = "month"


class UserRule(Base):
    __tablename__ = "user_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=True
    )
    text: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    regularity: Mapped[Regularity] = mapped_column(
        Enum(Regularity, name="regularity_enum"), nullable=False
    )
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    start_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=False,
    )

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="user_rules"
    )

    author: Mapped["User"] = relationship(
        "User", foreign_keys=[author_id], back_populates="authored_rules"
    )


class StateRule(Base):
    __tablename__ = "state_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_state: Mapped[State] = mapped_column(
        Enum(State, name="state_enum"), nullable=False,
    )
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=True
    )
    text: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    regularity: Mapped[Regularity] = mapped_column(
        Enum(Regularity, name="regularity_enum"), nullable=False,
    )
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=False,
    )
    offset_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    author: Mapped["User"] = relationship("User")
