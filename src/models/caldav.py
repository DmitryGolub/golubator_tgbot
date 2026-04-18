from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class CalDAVSyncStatus(enum.Enum):
    pending = "pending"
    synced = "synced"
    failed = "failed"


class CalDAVAccount(Base):
    __tablename__ = "caldav_accounts"
    __table_args__ = {"schema": "integrations"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"),
        unique=True,
        nullable=False,
    )
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)

    principal_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    calendar_home_url: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    default_calendar_url: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    calendar_display_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    sync_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    sync_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ctag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_pulled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_pull_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_pull_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CalDAVAccount id={self.id} telegram_id={self.telegram_id} "
            f"base_url={self.base_url!r} username={self.username!r} "
            f"encrypted_password=<redacted>>"
        )


class CalDAVEventLink(Base):
    __tablename__ = "caldav_event_links"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id", "account_id", name="uq_caldav_event_links_meeting_account"
        ),
        Index("ix_caldav_event_links_account", "account_id"),
        {"schema": "integrations"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("integrations.caldav_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    meeting_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    event_href: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    etag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[CalDAVSyncStatus] = mapped_column(
        Enum(
            CalDAVSyncStatus,
            name="caldav_sync_status_enum",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            create_type=False,
            schema="integrations",
        ),
        nullable=False,
        default=CalDAVSyncStatus.pending,
        server_default=CalDAVSyncStatus.pending.value,
    )
    last_pushed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    remote_last_modified: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    remote_sequence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_pulled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
