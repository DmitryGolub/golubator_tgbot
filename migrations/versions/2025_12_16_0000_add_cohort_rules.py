"""add cohort rules

Revision ID: add_cohort_rules
Revises: add_last_sent_at_state_rules
Create Date: 2025-12-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_cohort_rules"
down_revision: Union[str, Sequence[str], None] = "add_last_sent_at_state_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cohort_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cohort_id", sa.BigInteger(), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "regularity",
            postgresql.ENUM(
                "day",
                "week",
                "fortnight",
                "month",
                name="regularity_enum",
                create_type=False,  # enum already exists
            ),
            nullable=False,
        ),
        sa.Column("author_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cohort_rules")
