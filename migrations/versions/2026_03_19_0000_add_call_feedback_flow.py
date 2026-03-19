"""add call flow and mentor feedback

Revision ID: add_call_feedback_flow
Revises: add_cohort_rules
Create Date: 2026-03-19 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_call_feedback_flow"
down_revision: Union[str, Sequence[str], None] = "add_cohort_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("meetings", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    call_status_enum = postgresql.ENUM(
        "идёт",
        "завершён",
        name="call_status_enum",
        create_type=False,
    )
    call_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "meeting_id",
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
        sa.Column(
            "student_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            call_status_enum,
            nullable=False,
            server_default=sa.text("'идёт'"),
        ),
        sa.UniqueConstraint("meeting_id", name="uq_calls_meeting_id"),
    )
    op.create_index("ix_calls_meeting_id", "calls", ["meeting_id"], unique=True)
    op.create_index("ix_calls_mentor_id", "calls", ["mentor_id"])
    op.create_index("ix_calls_student_id", "calls", ["student_id"])

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
    op.create_index("ix_mentor_feedback_call_id", "mentor_feedback", ["call_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_mentor_feedback_call_id", table_name="mentor_feedback")
    op.drop_table("mentor_feedback")

    op.drop_index("ix_calls_student_id", table_name="calls")
    op.drop_index("ix_calls_mentor_id", table_name="calls")
    op.drop_index("ix_calls_meeting_id", table_name="calls")
    op.drop_table("calls")
    op.execute("DROP TYPE IF EXISTS call_status_enum")

    op.drop_column("meetings", "completed_at")
