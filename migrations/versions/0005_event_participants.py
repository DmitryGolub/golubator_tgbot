"""Add event_participants recipient type.

Revision ID: 0005_event_participants
Revises: 0004_drop_placeholder
Create Date: 2026-04-12 00:00:00.000000

"""

from alembic import op

revision = "0005_event_participants"
down_revision = "0004_drop_placeholder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE recipient_type_enum ADD VALUE IF NOT EXISTS 'event_participants'"
    )
    op.execute(
        "UPDATE triggers.trigger_rules "
        "SET recipient_type = 'event_participants' "
        "WHERE name IN ('Уведомление о созвоне', 'Напоминание за 5 минут')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE triggers.trigger_rules "
        "SET recipient_type = 'event_student' "
        "WHERE name IN ('Уведомление о созвоне', 'Напоминание за 5 минут')"
    )
    # PostgreSQL does not support removing enum values; skip enum rollback.
