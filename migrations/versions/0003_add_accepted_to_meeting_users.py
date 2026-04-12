"""Add accepted column to meeting_users.

Revision ID: 0003_accepted
Revises: 0002_seed
Create Date: 2026-04-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_accepted"
down_revision: Union[str, None] = "0002_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meeting_users",
        sa.Column("accepted", sa.Boolean(), nullable=True),
        schema="meetings",
    )


def downgrade() -> None:
    op.drop_column("meeting_users", "accepted", schema="meetings")
