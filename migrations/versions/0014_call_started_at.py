"""Add call_started_at to meetings, channel_id to mentors, update Lead→Study texts.

Revision ID: 0014_call_started_at
Revises: 0013_drop_active_mentor_idx
Create Date: 2026-04-05 00:00:14.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_call_started_at"
down_revision: Union[str, None] = "0013_drop_active_mentor_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("call_started_at", sa.DateTime(timezone=True), nullable=True),
        schema="meetings",
    )

    op.add_column(
        "mentors",
        sa.Column("channel_id", sa.BigInteger(), nullable=True),
        schema="iam",
    )

    # Replace 6 per-category Lead→Study rules with a single universal one
    conn = op.get_bind()

    conn.execute(
        sa.text("DELETE FROM triggers.trigger_rules WHERE name LIKE 'Lead→Study:%'")
    )

    LEAD_TO_STUDY_TEXT = (
        "Добро пожаловать в Голубятню! 🎉\n\n"
        "Ты подключён(а) к программе сопровождения.\n\n"
        "Вступай в чаты:\n"
        "— Общий чат: $general_chat_link\n"
        "— Канал ментора: $mentor_channel_link"
    )

    rules_t = sa.table(
        "trigger_rules",
        sa.column("name"),
        sa.column("trigger_type"),
        sa.column("action_type"),
        sa.column("is_active"),
        sa.column("delay_seconds"),
        sa.column("delay_mode"),
        sa.column("recipient_type"),
        sa.column("recipient_config"),
        sa.column("action_config"),
        sa.column("trigger_config"),
        schema="triggers",
    )

    conn.execute(
        rules_t.insert().values(
            name="Lead→Study: Welcome",
            trigger_type="cohort_changed",
            action_type="send_notification",
            is_active=True,
            delay_seconds=0,
            delay_mode="after_trigger",
            recipient_type="event_user",
            recipient_config=None,
            action_config=sa.text(
                '\'{"text": "' + LEAD_TO_STUDY_TEXT.replace("\n", "\\n") + "\"}'::jsonb"
            ),
            trigger_config=sa.text(
                '\'{"cohort_type": "Status", '
                '"from_value": "Lead", '
                '"to_value": "Study"}\'::jsonb'
            ),
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Remove the single universal rule and restore 6 per-category rules
    conn.execute(
        sa.text("DELETE FROM triggers.trigger_rules WHERE name = 'Lead→Study: Welcome'")
    )

    OLD_RULES = [
        ("Lead→Study: Backend", "Backend", "Backend"),
        ("Lead→Study: Frontend", "Frontend", "Frontend"),
        ("Lead→Study: Design", "Design", "Design"),
        ("Lead→Study: QA", "QA", "QA"),
        ("Lead→Study: Analytics", "Analytics", "Analytics"),
    ]

    rules_t = sa.table(
        "trigger_rules",
        sa.column("name"),
        sa.column("trigger_type"),
        sa.column("action_type"),
        sa.column("is_active"),
        sa.column("delay_seconds"),
        sa.column("delay_mode"),
        sa.column("recipient_type"),
        sa.column("recipient_config"),
        sa.column("action_config"),
        sa.column("trigger_config"),
        schema="triggers",
    )

    for rule_name, category, direction in OLD_RULES:
        text = (
            f"Добро пожаловать в Голубятню! 🎉\\n\\n"
            f"Ты зачислен(а) на направление {direction}.\\n\\n"
            f"Вступай в чаты:\\n"
            f"— Общий чат: [ССЫЛКА]\\n"
            f"— {direction}: [ССЫЛКА]"
        )
        conn.execute(
            rules_t.insert().values(
                name=rule_name,
                trigger_type="cohort_changed",
                action_type="send_notification",
                is_active=True,
                delay_seconds=0,
                delay_mode="after_trigger",
                recipient_type="event_user",
                recipient_config=None,
                action_config=sa.text(f"'{json_obj(text)}'::jsonb"),
                trigger_config=sa.text(
                    f'{{"cohort_type": "Status", '
                    f'"from_value": "Lead", '
                    f'"to_value": "Study", '
                    f'"require_category": "{category}"}}'
                    "::jsonb"
                ),
            )
        )

    # Fallback rule
    fallback_text = (
        "Добро пожаловать в Голубятню! 🎉\\n\\n"
        "Ты подключён(а) к программе сопровождения.\\n\\n"
        "Вступай в общий чат: [ССЫЛКА]\\n\\n"
        "Направление пока не указано — обратись к куратору."
    )
    conn.execute(
        rules_t.insert().values(
            name="Lead→Study: Fallback (no category)",
            trigger_type="cohort_changed",
            action_type="send_notification",
            is_active=True,
            delay_seconds=0,
            delay_mode="after_trigger",
            recipient_type="event_user",
            recipient_config=None,
            action_config=sa.text(f"'{json_obj(fallback_text)}'::jsonb"),
            trigger_config=sa.text(
                '\'{"cohort_type": "Status", '
                '"from_value": "Lead", '
                '"to_value": "Study", '
                '"require_category": "__none__"}\'::jsonb'
            ),
        )
    )

    op.drop_column("mentors", "channel_id", schema="iam")
    op.drop_column("meetings", "call_started_at", schema="meetings")


def json_obj(text: str) -> str:
    return '{"text": "' + text + '"}'
