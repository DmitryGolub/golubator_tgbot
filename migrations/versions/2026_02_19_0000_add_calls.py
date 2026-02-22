"""add calls

Revision ID: add_calls
Revises: add_cohort_rules
Create Date: 2026-02-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_calls"
down_revision: Union[str, Sequence[str], None] = "add_cohort_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
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
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "status",
            call_status_enum,
            nullable=False,
            server_default=sa.text("'идёт'"),
        ),
    )
    op.create_index("ix_calls_mentor_id", "calls", ["mentor_id"])
    op.create_index("ix_calls_student_id", "calls", ["student_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_calls_student_id", table_name="calls")
    op.drop_index("ix_calls_mentor_id", table_name="calls")
    op.drop_table("calls")
    op.execute("DROP TYPE IF EXISTS call_status_enum")
