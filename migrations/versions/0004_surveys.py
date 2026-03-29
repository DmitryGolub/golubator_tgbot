"""Surveys schema tables: templates, questions, options, sessions, answers.

Revision ID: 0004_surveys
Revises: 0003_meetings
Create Date: 2026-03-22 00:00:03.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

revision: str = "0004_surveys"
down_revision: Union[str, None] = "0003_meetings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

question_type_enum = pgEnum(
    "text",
    "rating",
    "single_choice",
    "multiple_choice",
    name="question_type_enum",
    create_type=False,
)
session_status_enum = pgEnum(
    "pending", "in_progress", "completed", name="session_status_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "survey_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "target_role_id",
            sa.Integer,
            sa.ForeignKey("iam.roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_by",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="surveys",
    )
    op.create_table(
        "survey_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("question_type", question_type_enum, nullable=False),
        sa.Column(
            "is_required", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "template_id", "sort_order", name="uq_survey_question_order"
        ),
        schema="surveys",
    )
    op.create_table(
        "survey_question_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.UniqueConstraint("question_id", "sort_order", name="uq_survey_option_order"),
        schema="surveys",
    )
    op.create_table(
        "survey_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "respondent_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("context_type", sa.String(32), nullable=True),
        sa.Column("context_id", sa.String(64), nullable=True),
        sa.Column(
            "status", session_status_enum, nullable=False, server_default="pending"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "template_id",
            "respondent_id",
            "context_type",
            "context_id",
            name="uq_survey_session_unique",
        ),
        schema="surveys",
    )
    op.create_index(
        "uq_survey_session_no_ctx",
        "survey_sessions",
        ["template_id", "respondent_id"],
        unique=True,
        schema="surveys",
        postgresql_where=sa.text("context_type IS NULL AND context_id IS NULL"),
    )
    op.create_table(
        "survey_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value_text", sa.Text, nullable=True),
        sa.Column("value_int", sa.Integer, nullable=True),
        sa.Column("value_choice", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "session_id", "question_id", name="uq_survey_answer_unique"
        ),
        schema="surveys",
    )


def downgrade() -> None:
    op.drop_table("survey_answers", schema="surveys")
    op.drop_index(
        "uq_survey_session_no_ctx", table_name="survey_sessions", schema="surveys"
    )
    op.drop_table("survey_sessions", schema="surveys")
    op.drop_table("survey_question_options", schema="surveys")
    op.drop_table("survey_questions", schema="surveys")
    op.drop_table("survey_templates", schema="surveys")
