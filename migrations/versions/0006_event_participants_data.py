"""Update trigger rules to use event_participants recipient type.

Revision ID: 0006_event_participants_data
Revises: 0005_event_participants_enum
Create Date: 2026-04-12 00:00:00.000000

"""

from alembic import op

revision = "0006_event_participants_data"
down_revision = "0005_event_participants_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
