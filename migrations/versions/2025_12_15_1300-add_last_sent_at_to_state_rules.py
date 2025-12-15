"""add last_sent_at to state_rules

Revision ID: add_last_sent_at_state_rules
Revises: 435ea526d448
Create Date: 2025-12-15 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_last_sent_at_state_rules"
down_revision: Union[str, Sequence[str], None] = "435ea526d448"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "state_rules",
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("state_rules", "last_sent_at")
