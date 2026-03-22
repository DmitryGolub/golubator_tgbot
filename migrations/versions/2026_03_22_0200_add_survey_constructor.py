"""Add survey constructor tables: survey_templates, survey_questions,
survey_question_options, survey_sessions, survey_answers.

Revision ID: add_survey_constructor
Revises: notion_cohorts
Create Date: 2026-03-22 02:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_survey_constructor"
down_revision: Union[str, None] = "notion_cohorts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


question_type_enum = sa.Enum(
    "text", "rating", "single_choice", "multiple_choice",
    name="question_type_enum",
)
session_status_enum = sa.Enum(
    "pending", "in_progress", "completed",
    name="session_status_enum",
)


def upgrade() -> None:
    question_type_enum.create(op.get_bind(), checkfirst=True)
    session_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "survey_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "target_role_id",
            sa.Integer,
            sa.ForeignKey("roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by",
            sa.BigInteger,
            sa.ForeignKey("users.telegram_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "survey_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("survey_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("question_type", question_type_enum, nullable=False),
        sa.Column("is_required", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("template_id", "sort_order", name="uq_survey_question_order"),
    )

    op.create_table(
        "survey_question_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("survey_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.UniqueConstraint("question_id", "sort_order", name="uq_survey_option_order"),
    )

    op.create_table(
        "survey_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("survey_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "respondent_id",
            sa.BigInteger,
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("context_type", sa.String(32), nullable=True),
        sa.Column("context_id", sa.String(64), nullable=True),
        sa.Column(
            "status",
            session_status_enum,
            nullable=False,
            server_default="pending",
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
    )

    op.create_table(
        "survey_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer,
            sa.ForeignKey("survey_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("survey_questions.id", ondelete="CASCADE"),
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
        sa.UniqueConstraint("session_id", "question_id", name="uq_survey_answer_unique"),
    )

    # Add manage_surveys permission
    permissions_table = sa.table(
        "permissions",
        sa.column("codename", sa.String),
        sa.column("description", sa.String),
    )
    op.execute(
        permissions_table.insert().values(
            codename="manage_surveys",
            description="Управление шаблонами опросов",
        )
    )


def downgrade() -> None:
    permissions_table = sa.table(
        "permissions",
        sa.column("codename", sa.String),
    )
    op.execute(
        permissions_table.delete().where(permissions_table.c.codename == "manage_surveys")
    )
    op.drop_table("survey_answers")
    op.drop_table("survey_sessions")
    op.drop_table("survey_question_options")
    op.drop_table("survey_questions")
    op.drop_table("survey_templates")
    session_status_enum.drop(op.get_bind(), checkfirst=True)
    question_type_enum.drop(op.get_bind(), checkfirst=True)
