"""Seed survey templates from hardcoded surveys:
post_call_student, mentor_feedback, mentor_self_review.

Revision ID: seed_survey_templates
Revises: add_survey_constructor
Create Date: 2026-03-22 03:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "seed_survey_templates"
down_revision: Union[str, None] = "add_survey_constructor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


templates_table = sa.table(
    "survey_templates",
    sa.column("id", sa.Integer),
    sa.column("title", sa.String),
    sa.column("slug", sa.String),
    sa.column("description", sa.Text),
    sa.column("is_active", sa.Boolean),
)

questions_table = sa.table(
    "survey_questions",
    sa.column("id", sa.Integer),
    sa.column("template_id", sa.Integer),
    sa.column("sort_order", sa.Integer),
    sa.column("title", sa.String),
    sa.column("question_type", sa.String),
    sa.column("is_required", sa.Boolean),
    sa.column("config", sa.JSON),
)

options_table = sa.table(
    "survey_question_options",
    sa.column("id", sa.Integer),
    sa.column("question_id", sa.Integer),
    sa.column("sort_order", sa.Integer),
    sa.column("value", sa.String),
    sa.column("label", sa.String),
)


TEMPLATES = [
    {
        "slug": "post_call_student",
        "title": "Опрос ученика после созвона",
        "description": "Заполняется учеником после завершённого созвона с ментором",
        "questions": [
            {
                "sort_order": 1,
                "title": "Длительность созвона",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "lt_30", "label": "<30 минут"},
                    {"value": "30_45", "label": "30-45 минут"},
                    {"value": "45_60", "label": "45-60 минут"},
                    {"value": "gt_60", "label": ">60 минут"},
                ],
            },
            {
                "sort_order": 2,
                "title": "Стиль общения ментора",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 5},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Глубина проверки знаний",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 5},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Насколько ученик понял материал",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 5},
                "options": [],
            },
            {
                "sort_order": 5,
                "title": "Комментарий",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "mentor_feedback",
        "title": "Фидбек ментора после созвона",
        "description": "Заполняется ментором после завершённого созвона с учеником",
        "questions": [
            {
                "sort_order": 1,
                "title": "Готовность ученика",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "not_ready", "label": "Не готов"},
                    {"value": "bad", "label": "Плохо"},
                    {"value": "ok", "label": "Нормально"},
                    {"value": "great", "label": "Отлично"},
                ],
            },
            {
                "sort_order": 2,
                "title": "Длительность созвона",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "lt_30", "label": "До 30 минут"},
                    {"value": "min_30_60", "label": "30-60 минут"},
                    {"value": "min_60_90", "label": "60-90 минут"},
                    {"value": "ge_90", "label": "90+ минут"},
                ],
            },
            {
                "sort_order": 3,
                "title": "Мотивация ученика",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 5},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Стадия нейромутации",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 5,
                "title": "Комментарий",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "mentor_self_review",
        "title": "Ежемесячная самооценка ментора",
        "description": "Заполняется ментором раз в месяц",
        "questions": [
            {
                "sort_order": 1,
                "title": "Оцените вашу загрузку",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 5},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Раздражение тупостью голубя",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 5},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Средняя нейромутация учеников",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Комментарий",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    for tmpl in TEMPLATES:
        result = conn.execute(
            templates_table.insert()
            .values(
                title=tmpl["title"],
                slug=tmpl["slug"],
                description=tmpl["description"],
                is_active=True,
            )
            .returning(templates_table.c.id)
        )
        template_id = result.scalar_one()

        for q in tmpl["questions"]:
            q_result = conn.execute(
                questions_table.insert()
                .values(
                    template_id=template_id,
                    sort_order=q["sort_order"],
                    title=q["title"],
                    question_type=q["question_type"],
                    is_required=q["is_required"],
                    config=q["config"],
                )
                .returning(questions_table.c.id)
            )
            question_id = q_result.scalar_one()

            for i, opt in enumerate(q["options"]):
                conn.execute(
                    options_table.insert().values(
                        question_id=question_id,
                        sort_order=i + 1,
                        value=opt["value"],
                        label=opt["label"],
                    )
                )


def downgrade() -> None:
    conn = op.get_bind()
    for tmpl in TEMPLATES:
        conn.execute(
            templates_table.delete().where(templates_table.c.slug == tmpl["slug"])
        )
