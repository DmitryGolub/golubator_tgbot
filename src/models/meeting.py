from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Optional
from datetime import datetime
from sqlalchemy import (
    Enum,
    Index,
    Integer,
    BigInteger,
    Text,
    String,
    DateTime,
    ForeignKey,
    func,
    text,
)

if TYPE_CHECKING:
    from src.models.user import User
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base


class CallStatus(enum.Enum):
    ongoing = "идёт"
    finished = "завершён"


class ProposalStatus(enum.Enum):
    pending_confirmation = "ожидает_подтверждения"
    confirmed = "подтверждён"


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        Index(
            "ix_meetings_active_mentor",
            "mentor_telegram_id",
            unique=True,
            postgresql_where=text("call_status = 'идёт'"),
        ),
        {"schema": "meetings"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    meeting_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Notion sync fields
    notion_page_id: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, index=True, nullable=True
    )
    event_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    topic: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    mentor_telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    mentee_telegram_tag: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    recording_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_items: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    call_status: Mapped[Optional[CallStatus]] = mapped_column(
        Enum(
            CallStatus,
            name="call_status_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            create_type=False,
        ),
        nullable=True,
    )
    student_telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
    proposal_status: Mapped[Optional[ProposalStatus]] = mapped_column(
        Enum(
            ProposalStatus,
            name="proposal_status_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            create_type=False,
            schema="meetings",
        ),
        nullable=True,
    )
    proposed_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    original_scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    participants: Mapped[list["User"]] = relationship(
        "User",
        secondary="meetings.meeting_users",
        back_populates="meetings",
        lazy="selectin",
    )
    student: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[student_telegram_id],
        lazy="selectin",
        overlaps="proposer",
    )
    proposer: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[proposed_by],
        lazy="selectin",
        overlaps="student",
    )


class MeetingUser(Base):
    __tablename__ = "meeting_users"

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.meetings.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        Index("ix_meeting_users_user_id", "user_id"),
        {"schema": "meetings"},
    )
