"""Add trigger system: trigger_rules, trigger_executions tables + permissions.

Revision ID: add_triggers
Revises: seed_survey_templates
Create Date: 2026-03-22 04:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_triggers"
down_revision: Union[str, None] = "seed_survey_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


trigger_type_enum = sa.Enum(
    "meeting_created", "call_ended", "periodic_cron", "user_state_changed", "manual",
    name="trigger_type_enum",
)
action_type_enum = sa.Enum(
    "send_notification", "send_survey",
    name="action_type_enum",
)
delay_mode_enum = sa.Enum(
    "after_trigger", "before_scheduled",
    name="delay_mode_enum",
)
recipient_type_enum = sa.Enum(
    "event_student", "event_mentor", "by_role", "by_cohort", "by_state", "by_tag", "specific_users",
    name="recipient_type_enum",
)
trigger_regularity_enum = sa.Enum(
    "day", "week", "fortnight", "month",
    name="trigger_regularity_enum",
)
execution_status_enum = sa.Enum(
    "pending", "sent", "failed",
    name="execution_status_enum",
)


def upgrade() -> None:
    trigger_type_enum.create(op.get_bind(), checkfirst=True)
    action_type_enum.create(op.get_bind(), checkfirst=True)
    delay_mode_enum.create(op.get_bind(), checkfirst=True)
    recipient_type_enum.create(op.get_bind(), checkfirst=True)
    trigger_regularity_enum.create(op.get_bind(), checkfirst=True)
    execution_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "trigger_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger_type", trigger_type_enum, nullable=False),
        sa.Column("action_type", action_type_enum, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("cron_expression", sa.String(64), nullable=True),
        sa.Column("regularity", trigger_regularity_enum, nullable=True),
        sa.Column("time_of_day", sa.Time, nullable=True),
        sa.Column("delay_seconds", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("delay_mode", delay_mode_enum, nullable=False, server_default="after_trigger"),
        sa.Column("recipient_type", recipient_type_enum, nullable=False),
        sa.Column("recipient_config", sa.JSON, nullable=True),
        sa.Column("action_config", sa.JSON, nullable=False),
        sa.Column(
            "created_by", sa.BigInteger,
            sa.ForeignKey("users.telegram_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "trigger_executions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "rule_id", sa.Integer,
            sa.ForeignKey("trigger_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(128), nullable=True),
        sa.Column(
            "recipient_id", sa.BigInteger,
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", execution_status_enum, nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rule_id", "event_key", "recipient_id", name="uq_trigger_execution_unique"),
    )

    # Add permissions
    permissions_table = sa.table(
        "permissions",
        sa.column("codename", sa.String),
        sa.column("description", sa.String),
    )
    op.execute(
        permissions_table.insert().values([
            {"codename": "manage_triggers", "description": "Управление триггерными правилами"},
            {"codename": "send_manual", "description": "Ручная и отложенная отправка"},
        ])
    )


def downgrade() -> None:
    permissions_table = sa.table(
        "permissions",
        sa.column("codename", sa.String),
    )
    op.execute(
        permissions_table.delete().where(
            permissions_table.c.codename.in_(["manage_triggers", "send_manual"])
        )
    )

    op.drop_table("trigger_executions")
    op.drop_table("trigger_rules")

    execution_status_enum.drop(op.get_bind(), checkfirst=True)
    trigger_regularity_enum.drop(op.get_bind(), checkfirst=True)
    recipient_type_enum.drop(op.get_bind(), checkfirst=True)
    delay_mode_enum.drop(op.get_bind(), checkfirst=True)
    action_type_enum.drop(op.get_bind(), checkfirst=True)
    trigger_type_enum.drop(op.get_bind(), checkfirst=True)
