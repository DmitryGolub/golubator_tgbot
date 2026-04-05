"""Drop partial unique index ix_meetings_active_mentor.

The constraint is no longer needed: meetings now support multiple mentors
as participants, and the "one active call per meeting" invariant is already
enforced by the call_status IS NULL check in start_call.

Revision ID: 0013_drop_active_mentor_idx
Revises: 0012_is_cancelled
Create Date: 2026-04-05 00:00:13.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0013_drop_active_mentor_idx"
down_revision: Union[str, None] = "0012_is_cancelled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_meetings_active_mentor",
        table_name="meetings",
        schema="meetings",
    )


def downgrade() -> None:
    op.create_index(
        "ix_meetings_active_mentor",
        "meetings",
        ["mentor_telegram_id"],
        unique=True,
        schema="meetings",
        postgresql_where="call_status = 'идёт'",
    )
