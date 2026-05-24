"""Call duration survey.

Revision ID: 0007_call_duration_survey
Revises: 0006_off_meeting_created_notify
Create Date: 2026-05-20 20:00:00.000000
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_call_duration_survey"
down_revision: Union[str, None] = "0006_off_meeting_created_notify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CALL_DURATION_TEMPLATE_SLUG = "call_duration_actual"

CALL_DURATION_QUESTION_CONFIG = {
    "input_type": "positive_int_minutes",
    "min": 1,
    "max": 1440,
    "quick_options": [
        {"value": "15", "label": "15 мин"},
        {"value": "30", "label": "30 мин"},
        {"value": "45", "label": "45 мин"},
        {"value": "60", "label": "60 мин"},
    ],
}


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("actual_duration_minutes", sa.Integer(), nullable=True),
        schema="meetings",
    )
    op.add_column(
        "meetings",
        sa.Column(
            "duration_answered_by",
            sa.BigInteger(),
            sa.ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="meetings",
    )
    op.create_check_constraint(
        "ck_meetings_actual_duration_minutes_range",
        "meetings",
        "actual_duration_minutes IS NULL OR "
        "(actual_duration_minutes > 0 AND actual_duration_minutes <= 1440)",
        schema="meetings",
    )

    op.add_column(
        "survey_templates",
        sa.Column("reminder_interval_minutes", sa.Integer(), nullable=True),
        schema="surveys",
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO surveys.survey_templates "
            "(title, slug, kind, description, body, is_active, reminder_interval_minutes) "
            "VALUES ("
            " :title, :slug, CAST('survey' AS surveys.template_kind_enum), "
            " :description, :body, true, :reminder_interval_minutes"
            ") "
            "ON CONFLICT (slug) DO UPDATE SET "
            " title = EXCLUDED.title, "
            " description = EXCLUDED.description, "
            " body = EXCLUDED.body, "
            " reminder_interval_minutes = EXCLUDED.reminder_interval_minutes, "
            " is_active = true"
        ),
        {
            "title": "Фактическая длительность созвона",
            "slug": CALL_DURATION_TEMPLATE_SLUG,
            "description": (
                "Запрашивает у организатора фактическую длительность активного созвона"
            ),
            "body": "⏱ Напоминание: укажите фактическую длительность созвона в минутах.",
            "reminder_interval_minutes": 30,
        },
    )
    template_id = conn.execute(
        sa.text("SELECT id FROM surveys.survey_templates WHERE slug = :slug"),
        {"slug": CALL_DURATION_TEMPLATE_SLUG},
    ).scalar_one()
    conn.execute(
        sa.text(
            "INSERT INTO surveys.survey_questions "
            "(template_id, sort_order, title, question_type, is_required, config) "
            "VALUES ("
            " :template_id, 1, :title, 'text', true, CAST(:config AS jsonb)"
            ") "
            "ON CONFLICT ON CONSTRAINT uq_survey_question_order DO UPDATE SET "
            " title = EXCLUDED.title, "
            " question_type = EXCLUDED.question_type, "
            " is_required = EXCLUDED.is_required, "
            " config = EXCLUDED.config"
        ),
        {
            "template_id": template_id,
            "title": "Введите фактическую длительность созвона в минутах",
            "config": json.dumps(CALL_DURATION_QUESTION_CONFIG),
        },
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM surveys.survey_templates WHERE slug = :slug").bindparams(
            slug=CALL_DURATION_TEMPLATE_SLUG
        )
    )

    op.drop_column("survey_templates", "reminder_interval_minutes", schema="surveys")

    op.drop_constraint(
        "ck_meetings_actual_duration_minutes_range",
        "meetings",
        schema="meetings",
        type_="check",
    )
    op.drop_column("meetings", "duration_answered_by", schema="meetings")
    op.drop_column("meetings", "actual_duration_minutes", schema="meetings")
