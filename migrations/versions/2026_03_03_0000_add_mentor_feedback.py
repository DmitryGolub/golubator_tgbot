"""add mentor feedback

Revision ID: add_mentor_feedback
Revises: add_calls
Create Date: 2026-03-03 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_mentor_feedback"
down_revision: Union[str, Sequence[str], None] = "add_calls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mentor_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "call_id",
            sa.Integer(),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mentor_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration", sa.String(length=32), nullable=False),
        sa.Column("motivation", sa.Integer(), nullable=False),
        sa.Column("neuromutation_stage", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('not_ready', 'bad', 'ok', 'great')",
            name="ck_mentor_feedback_status",
        ),
        sa.CheckConstraint(
            "duration IN ('lt_30', 'min_30_60', 'min_60_90', 'ge_90')",
            name="ck_mentor_feedback_duration",
        ),
        sa.CheckConstraint(
            "motivation BETWEEN 1 AND 5",
            name="ck_mentor_feedback_motivation_range",
        ),
        sa.CheckConstraint(
            "neuromutation_stage BETWEEN 1 AND 10",
            name="ck_mentor_feedback_neuromutation_stage_range",
        ),
    )
    op.create_index(
        "ix_mentor_feedback_call_id",
        "mentor_feedback",
        ["call_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_mentor_feedback_call_id", table_name="mentor_feedback")
    op.drop_table("mentor_feedback")
