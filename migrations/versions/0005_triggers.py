"""Triggers schema tables: trigger_rules, trigger_executions.

Revision ID: 0005_triggers
Revises: 0004_surveys
Create Date: 2026-03-22 00:00:04.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

revision: str = "0005_triggers"
down_revision: Union[str, None] = "0004_surveys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

trigger_type_enum = pgEnum(
    "meeting_created",
    "call_ended",
    "periodic_cron",
    "cohort_changed",
    "manual",
    name="trigger_type_enum",
    create_type=False,
)
action_type_enum = pgEnum(
    "send_notification", "send_survey", name="action_type_enum", create_type=False
)
delay_mode_enum = pgEnum(
    "after_trigger", "before_scheduled", name="delay_mode_enum", create_type=False
)
recipient_type_enum = pgEnum(
    "event_student",
    "event_mentor",
    "event_user",
    "by_role",
    "by_cohort",
    "by_state",
    "specific_users",
    "direction_lead",
    name="recipient_type_enum",
    create_type=False,
)
trigger_regularity_enum = pgEnum(
    "day",
    "week",
    "fortnight",
    "month",
    name="trigger_regularity_enum",
    create_type=False,
)
execution_status_enum = pgEnum(
    "pending", "sent", "failed", name="execution_status_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "trigger_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger_type", trigger_type_enum, nullable=False),
        sa.Column("action_type", action_type_enum, nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("cron_expression", sa.String(64), nullable=True),
        sa.Column("regularity", trigger_regularity_enum, nullable=True),
        sa.Column("time_of_day", sa.Time, nullable=True),
        sa.Column(
            "delay_seconds", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "delay_mode",
            delay_mode_enum,
            nullable=False,
            server_default="after_trigger",
        ),
        sa.Column("recipient_type", recipient_type_enum, nullable=False),
        sa.Column("recipient_config", sa.JSON, nullable=True),
        sa.Column("action_config", sa.JSON, nullable=False),
        sa.Column("trigger_config", sa.JSON, nullable=True),
        sa.Column(
            "created_by",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema="triggers",
    )
    op.create_table(
        "trigger_executions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "rule_id",
            sa.Integer,
            sa.ForeignKey("triggers.trigger_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(128), nullable=True),
        sa.Column(
            "recipient_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "status", execution_status_enum, nullable=False, server_default="pending"
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "rule_id", "event_key", "recipient_id", name="uq_trigger_execution_unique"
        ),
        schema="triggers",
    )
    op.create_index(
        "ix_trigger_exec_pending",
        "trigger_executions",
        ["status", "scheduled_at"],
        schema="triggers",
    )
    op.create_index(
        "uq_trigger_exec_no_event_key",
        "trigger_executions",
        ["rule_id", "recipient_id"],
        unique=True,
        schema="triggers",
        postgresql_where=sa.text("event_key IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_trigger_exec_no_event_key",
        table_name="trigger_executions",
        schema="triggers",
    )
    op.drop_table("trigger_executions", schema="triggers")
    op.drop_table("trigger_rules", schema="triggers")
