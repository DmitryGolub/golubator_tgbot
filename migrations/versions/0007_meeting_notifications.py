"""Add meeting_notifications table and disable seed trigger 'Напоминание за 5 минут'.

Revision ID: 0007_meeting_notifications
Revises: 0006_off_meeting_created_notify
Create Date: 2026-05-24 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_meeting_notifications"
down_revision: Union[str, None] = "0006_off_meeting_created_notify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum(
                "confirmation_request",
                "reminder_repeat",
                "final_5min",
                "created",
                name="meeting_notification_type_enum",
                schema="meetings",
            ),
            nullable=False,
        ),
        sa.Column("scheduled_window", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                name="meeting_notification_status_enum",
                schema="meetings",
            ),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.meetings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "meeting_id",
            "user_id",
            "notification_type",
            "scheduled_window",
            name="uq_meeting_notification",
        ),
        schema="meetings",
    )

    # Disable legacy seed trigger to avoid duplicate 5-minute reminders
    op.execute(
        """
        UPDATE triggers.trigger_rules
           SET is_active = false
         WHERE name = 'Напоминание за 5 минут'
           AND trigger_type = 'meeting_created'
        """
    )


def downgrade() -> None:
    op.drop_table("meeting_notifications", schema="meetings")
    op.execute(
        """
        UPDATE triggers.trigger_rules
           SET is_active = true
         WHERE name = 'Напоминание за 5 минут'
           AND trigger_type = 'meeting_created'
        """
    )
