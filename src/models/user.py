from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, DateTime, func, Enum, ForeignKey, Integer, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.call import Call
    from src.models.meeting import Meeting
    from src.models.notification import Notification
    from src.models.notion_cache import NotionCohortCache
    from src.models.role import RoleModel
    from src.models.rule import UserRule
    from src.models.tag import Tag


class Role(enum.Enum):
    admin = "Админ"
    mentor = "Ментор"
    student = "Студент"


class State(enum.Enum):
    greeting = "Отбор"
    hold = "В ожидании"
    study = "Обучение"
    search = "Поиск работы"
    offer = "Оффер"


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="role_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=Role.student,
    )
    role_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("roles.id"), nullable=True
    )
    role_rel: Mapped["RoleModel | None"] = relationship(
        "RoleModel", back_populates="users", lazy="selectin"
    )
    state: Mapped[Optional[State]] = mapped_column(
        Enum(
            State,
            name="state_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
        default=State.greeting,
        server_default="Отбор",
    )

    mentor_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    notion_page_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
        index=True,
    )

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    state_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    meetings: Mapped[list["Meeting"]] = relationship(
        "Meeting",
        secondary="meeting_users",
        back_populates="participants",
        lazy="selectin",
    )
    cohort_cache: Mapped[list["NotionCohortCache"]] = relationship(
        "NotionCohortCache",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    mentor: Mapped[Optional["User"]] = relationship(
        "User",
        remote_side="User.telegram_id",
        back_populates="students",
    )
    students: Mapped[List["User"]] = relationship(
        "User",
        back_populates="mentor",
        cascade="all",
        passive_deletes=True,
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    user_rules: Mapped[list["UserRule"]] = relationship(
        "UserRule",
        back_populates="user",
        foreign_keys="UserRule.user_id",
        cascade="all, delete-orphan",
    )

    authored_rules: Mapped[list["UserRule"]] = relationship(
        "UserRule",
        back_populates="author",
        foreign_keys="UserRule.author_id",
    )
    mentor_calls: Mapped[list["Call"]] = relationship(
        "Call",
        foreign_keys="Call.mentor_id",
        back_populates="mentor",
        lazy="selectin",
    )
    student_calls: Mapped[list["Call"]] = relationship(
        "Call",
        foreign_keys="Call.student_id",
        back_populates="student",
        lazy="selectin",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary="user_tags",
        back_populates="users",
        lazy="selectin",
    )
