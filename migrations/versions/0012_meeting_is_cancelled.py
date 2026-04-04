"""Add meeting is_cancelled field.

Revision ID: 0012_is_cancelled
Revises: 0011_proposals
Create Date: 2026-04-04 00:00:12.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_is_cancelled"
down_revision: Union[str, None] = "0011_proposals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column(
            "is_cancelled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        schema="meetings",
    )


def downgrade() -> None:
    op.drop_column("meetings", "is_cancelled", schema="meetings")
