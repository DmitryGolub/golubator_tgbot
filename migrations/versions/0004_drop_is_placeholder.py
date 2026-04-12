"""Drop is_placeholder column from iam.users.

Revision ID: 0004_drop_placeholder
Revises: 0003_accepted
Create Date: 2026-04-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_drop_placeholder"
down_revision: Union[str, None] = "0003_accepted"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "is_placeholder", schema="iam")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_placeholder",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema="iam",
    )
