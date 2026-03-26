from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, DateTime, func, ForeignKey, Integer, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.meeting import Meeting
    from src.models.mentor import Mentor
    from src.models.mentee import Mentee
    from src.models.role import RoleModel
    from src.models.tag import Tag


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "iam"}

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    role_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("iam.roles.id"), nullable=True
    )
    role_rel: Mapped["RoleModel | None"] = relationship(
        "RoleModel", back_populates="users", lazy="selectin"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    meetings: Mapped[list["Meeting"]] = relationship(
        "Meeting",
        secondary="meetings.meeting_users",
        back_populates="participants",
        lazy="raise",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary="iam.user_tags",
        back_populates="users",
        lazy="raise",
    )
    mentor_profile: Mapped[Optional["Mentor"]] = relationship(
        "Mentor",
        back_populates="user",
        foreign_keys="Mentor.telegram_id",
        uselist=False,
        lazy="noload",
    )
    mentee_profile: Mapped[Optional["Mentee"]] = relationship(
        "Mentee",
        back_populates="user",
        foreign_keys="Mentee.telegram_id",
        uselist=False,
        lazy="noload",
    )
