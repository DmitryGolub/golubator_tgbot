"""Seed trigger rules replacing hardcoded notifications and survey triggers.

Revision ID: seed_trigger_rules
Revises: add_triggers
Create Date: 2026-03-22 05:00:00.000000
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "seed_trigger_rules"
down_revision: Union[str, None] = "add_triggers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


rules_table = sa.table(
    "trigger_rules",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("trigger_type", sa.String),
    sa.column("action_type", sa.String),
    sa.column("is_active", sa.Boolean),
    sa.column("cron_expression", sa.String),
    sa.column("delay_seconds", sa.Integer),
    sa.column("delay_mode", sa.String),
    sa.column("recipient_type", sa.String),
    sa.column("recipient_config", sa.JSON),
    sa.column("action_config", sa.JSON),
)

# Get survey template IDs by slug
templates_table = sa.table(
    "survey_templates",
    sa.column("id", sa.Integer),
    sa.column("slug", sa.String),
    sa.column("title", sa.String),
)


MEETING_NOTIFY_TEXT = (
    "<b>Вам назначен созвон.</b>\n"
    "Подробности можно узнать в меню бота."
)

MEETING_REMINDER_TEXT = (
    "<b>Напоминание о созвоне через ~5 минут.</b>\n"
    "Подготовьтесь к встрече."
)


def upgrade() -> None:
    conn = op.get_bind()

    # Look up template IDs
    def _get_template_id(slug: str) -> int | None:
        result = conn.execute(
            sa.select(templates_table.c.id, templates_table.c.title)
            .where(templates_table.c.slug == slug)
        )
        row = result.first()
        return (row.id, row.title) if row else (None, None)

    post_call_id, post_call_title = _get_template_id("post_call_student")
    feedback_id, feedback_title = _get_template_id("mentor_feedback")
    self_review_id, self_review_title = _get_template_id("mentor_self_review")

    rules = [
        {
            "name": "Уведомление о созвоне",
            "trigger_type": "meeting_created",
            "action_type": "send_notification",
            "is_active": True,
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_student",
            "recipient_config": None,
            "action_config": json.dumps({"text": MEETING_NOTIFY_TEXT}),
        },
        {
            "name": "Напоминание за 5 минут",
            "trigger_type": "meeting_created",
            "action_type": "send_notification",
            "is_active": True,
            "delay_seconds": 300,
            "delay_mode": "before_scheduled",
            "recipient_type": "event_student",
            "recipient_config": None,
            "action_config": json.dumps({"text": MEETING_REMINDER_TEXT}),
        },
    ]

    if post_call_id:
        rules.append({
            "name": "Опрос ученика после созвона",
            "trigger_type": "call_ended",
            "action_type": "send_survey",
            "is_active": True,
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_student",
            "recipient_config": None,
            "action_config": json.dumps({
                "survey_template_id": post_call_id,
                "survey_title": post_call_title,
            }),
        })

    if feedback_id:
        rules.append({
            "name": "Фидбек ментора после созвона",
            "trigger_type": "call_ended",
            "action_type": "send_survey",
            "is_active": True,
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_mentor",
            "recipient_config": None,
            "action_config": json.dumps({
                "survey_template_id": feedback_id,
                "survey_title": feedback_title,
            }),
        })

    if self_review_id:
        rules.append({
            "name": "Ежемесячная самооценка ментора",
            "trigger_type": "periodic_cron",
            "action_type": "send_survey",
            "is_active": True,
            "cron_expression": "0 9 1 * *",
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "by_role",
            "recipient_config": json.dumps({"role_name": "mentor"}),
            "action_config": json.dumps({
                "survey_template_id": self_review_id,
                "survey_title": self_review_title,
            }),
        })

    for rule in rules:
        conn.execute(rules_table.insert().values(**rule))


def downgrade() -> None:
    conn = op.get_bind()
    names = [
        "Уведомление о созвоне",
        "Напоминание за 5 минут",
        "Опрос ученика после созвона",
        "Фидбек ментора после созвона",
        "Ежемесячная самооценка ментора",
    ]
    for name in names:
        conn.execute(rules_table.delete().where(rules_table.c.name == name))
