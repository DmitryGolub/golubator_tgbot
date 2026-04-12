"""Add event_participants enum value.

Revision ID: 0005_event_participants_enum
Revises: 0004_drop_placeholder
Create Date: 2026-04-12 00:00:00.000000

"""

from alembic import op

revision = "0005_event_participants_enum"
down_revision = "0004_drop_placeholder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE recipient_type_enum ADD VALUE IF NOT EXISTS 'event_participants'"
        )


def downgrade() -> None:
    pass  # PostgreSQL does not support removing enum values
