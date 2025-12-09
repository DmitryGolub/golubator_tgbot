import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, DateTime, func, Enum, ForeignKey, Integer, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Role(enum.Enum):
    admin = "admin"
    mentor = "mentor"
    student = "student"


class State(enum.Enum):
    greeting = "greeting"
    hold = "hold"
    study = "study"
    search = "search"
    offer = "offer"


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    username: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    role: Mapped[Role] = mapped_column(
        Enum(Role, name="role_enum"), nullable=False, default=Role.student
    )
    state: Mapped[Optional[State]] = mapped_column(
        Enum(State, name="state_enum"), nullable=True, default=State.greeting, server_default="greeting",
    )

    mentor_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True,
    )
    cohort_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True,
    )

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    state_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    meetings: Mapped[list["Meeting"]] = relationship(
        "Meeting", secondary="meeting_users", back_populates="participants", lazy="selectin",
    )
    cohort: Mapped[Optional["Cohort"]] = relationship(
        "Cohort", back_populates="users", lazy="selectin",
    )
    mentor: Mapped[Optional["User"]] = relationship(
        "User", remote_side="User.telegram_id", back_populates="students",
    )
    students: Mapped[List["User"]] = relationship(
        "User", back_populates="mentor", cascade="all", passive_deletes=True,
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    user_rules: Mapped[list["UserRule"]] = relationship(
        "UserRule", back_populates="user", foreign_keys="UserRule.user_id", cascade="all, delete-orphan",
    )

    authored_rules: Mapped[list["UserRule"]] = relationship(
        "UserRule", back_populates="author", foreign_keys="UserRule.author_id",
    )