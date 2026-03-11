"""add mentor self review

Revision ID: add_mentor_self_review
Revises: add_mentor_feedback
Create Date: 2026-03-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_mentor_self_review"
down_revision: Union[str, Sequence[str], None] = "add_mentor_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mentor_self_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "mentor_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workload", sa.Integer(), nullable=False),
        sa.Column("pigeon_stupidity", sa.Integer(), nullable=False),
        sa.Column("avg_neuromutation", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "mentor_id",
            "period",
            name="uq_mentor_self_review_mentor_period",
        ),
        sa.CheckConstraint(
            "workload BETWEEN 1 AND 5",
            name="ck_mentor_self_review_workload_range",
        ),
        sa.CheckConstraint(
            "pigeon_stupidity BETWEEN 1 AND 5",
            name="ck_mentor_self_review_pigeon_stupidity_range",
        ),
        sa.CheckConstraint(
            "avg_neuromutation BETWEEN 1 AND 10",
            name="ck_mentor_self_review_avg_neuromutation_range",
        ),
        sa.CheckConstraint(
            "period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="ck_mentor_self_review_period_format",
        ),
    )
    op.create_index(
        "ix_mentor_self_reviews_mentor_id",
        "mentor_self_reviews",
        ["mentor_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_mentor_self_reviews_mentor_id", table_name="mentor_self_reviews")
    op.drop_table("mentor_self_reviews")
