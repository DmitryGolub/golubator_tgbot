from __future__ import annotations

import enum
from datetime import datetime, time
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
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.models.enums import Regularity


class TriggerType(str, enum.Enum):
    meeting_created = "meeting_created"
    call_ended = "call_ended"
    periodic_cron = "periodic_cron"
    cohort_changed = "cohort_changed"
    contract_signed = "contract_signed"
    manual = "manual"


class ActionType(str, enum.Enum):
    send_survey = "send_survey"


class DelayMode(str, enum.Enum):
    after_trigger = "after_trigger"
    before_scheduled = "before_scheduled"


class RecipientType(str, enum.Enum):
    event_student = "event_student"
    event_mentor = "event_mentor"
    event_user = "event_user"
    event_participants = "event_participants"
    by_role = "by_role"
    by_cohort = "by_cohort"
    by_state = "by_state"
    specific_users = "specific_users"
    direction_lead = "direction_lead"


class ExecutionStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    sent = "sent"
    failed = "failed"


trigger_type_enum = Enum(
    TriggerType,
    name="trigger_type_enum",
    values_callable=lambda e: [m.value for m in e],
)
action_type_enum = Enum(
    ActionType,
    name="action_type_enum",
    values_callable=lambda e: [m.value for m in e],
)
delay_mode_enum = Enum(
    DelayMode,
    name="delay_mode_enum",
    values_callable=lambda e: [m.value for m in e],
)
recipient_type_enum = Enum(
    RecipientType,
    name="recipient_type_enum",
    values_callable=lambda e: [m.value for m in e],
)
trigger_regularity_enum = Enum(
    Regularity,
    name="trigger_regularity_enum",
    values_callable=lambda e: [m.value for m in e],
)
execution_status_enum = Enum(
    ExecutionStatus,
    name="execution_status_enum",
    values_callable=lambda e: [m.value for m in e],
)


class TriggerRule(Base):
    __tablename__ = "trigger_rules"
    __table_args__ = {"schema": "triggers"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[TriggerType] = mapped_column(trigger_type_enum, nullable=False)
    action_type: Mapped[ActionType] = mapped_column(action_type_enum, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    # Periodic schedule (two modes)
    cron_expression: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    regularity: Mapped[Optional[Regularity]] = mapped_column(
        trigger_regularity_enum, nullable=True
    )
    time_of_day: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # Delay
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delay_mode: Mapped[DelayMode] = mapped_column(
        delay_mode_enum, nullable=False, default=DelayMode.after_trigger
    )

    # Recipients
    recipient_type: Mapped[RecipientType] = mapped_column(
        recipient_type_enum, nullable=False
    )
    recipient_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Action payload
    action_config: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Trigger-specific config (e.g. cohort_changed conditions)
    trigger_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Audit
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    executions: Mapped[list["TriggerExecution"]] = relationship(
        "TriggerExecution",
        back_populates="rule",
        lazy="noload",
        cascade="all, delete-orphan",
    )


class TriggerExecution(Base):
    __tablename__ = "trigger_executions"

    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "event_key",
            "recipient_id",
            name="uq_trigger_execution_unique",
        ),
        Index("ix_trigger_exec_pending", "status", "scheduled_at"),
        Index(
            "uq_trigger_exec_no_event_key",
            "rule_id",
            "recipient_id",
            unique=True,
            postgresql_where=text("event_key IS NULL"),
        ),
        {"schema": "triggers"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("triggers.trigger_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    recipient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        execution_status_enum,
        nullable=False,
        default=ExecutionStatus.pending,
        server_default=text("'pending'"),
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    rule: Mapped["TriggerRule"] = relationship(
        "TriggerRule",
        back_populates="executions",
        lazy="selectin",
    )
