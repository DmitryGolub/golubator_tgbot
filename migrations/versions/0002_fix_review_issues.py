"""Fix review issues: add trigger context, nullable author_id.

Revision ID: fix_review
Revises: init
Create Date: 2026-03-22 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fix_review"
down_revision: Union[str, None] = "init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # H3: Add context column to trigger_executions
    op.add_column(
        "trigger_executions",
        sa.Column("context", sa.JSON, nullable=True),
    )

    # H1: Fix nullable author_id (ondelete=SET NULL requires nullable)
    op.alter_column("user_rules", "author_id", existing_type=sa.BigInteger, nullable=True)
    op.alter_column("state_rules", "author_id", existing_type=sa.BigInteger, nullable=True)
    op.alter_column("cohort_rules", "author_id", existing_type=sa.BigInteger, nullable=True)


def downgrade() -> None:
    op.alter_column("cohort_rules", "author_id", existing_type=sa.BigInteger, nullable=False)
    op.alter_column("state_rules", "author_id", existing_type=sa.BigInteger, nullable=False)
    op.alter_column("user_rules", "author_id", existing_type=sa.BigInteger, nullable=False)
    op.drop_column("trigger_executions", "context")
