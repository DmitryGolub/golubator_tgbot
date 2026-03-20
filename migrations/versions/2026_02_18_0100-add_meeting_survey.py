"""add meeting survey

Revision ID: add_meeting_survey
Revises: add_cohort_rules
Create Date: 2026-02-18 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_meeting_survey"
down_revision: Union[str, Sequence[str], None] = "add_cohort_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("meetings", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meetings", sa.Column("survey_available_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "survey_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("duration_option", sa.String(length=32), nullable=False),
        sa.Column("mentor_style", sa.Integer(), nullable=False),
        sa.Column("knowledge_depth", sa.Integer(), nullable=False),
        sa.Column("understanding", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mentor_style BETWEEN 1 AND 5", name="ck_survey_response_mentor_style_range"),
        sa.CheckConstraint("knowledge_depth BETWEEN 1 AND 5", name="ck_survey_response_knowledge_depth_range"),
        sa.CheckConstraint("understanding BETWEEN 1 AND 5", name="ck_survey_response_understanding_range"),
        sa.CheckConstraint(
            "duration_option IN ('lt_30', '30_45', '45_60', 'gt_60')",
            name="ck_survey_response_duration_option",
        ),
        sa.UniqueConstraint("call_id", name="uq_survey_response_call_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("survey_responses")
    op.drop_column("meetings", "survey_available_at")
    op.drop_column("meetings", "completed_at")
