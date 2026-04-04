"""Create schemas and enums.

Revision ID: 0001_schemas
Revises: None
Create Date: 2026-03-22 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

revision: str = "0001_schemas"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

call_status_enum = pgEnum(
    "идёт", "завершён", name="call_status_enum", create_type=False
)
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
trigger_type_enum = pgEnum(
    "meeting_created",
    "call_ended",
    "periodic_cron",
    "cohort_changed",
    "manual",
    name="trigger_type_enum",
    create_type=False,
)
action_type_enum = pgEnum(
    "send_notification", "send_survey", name="action_type_enum", create_type=False
)
delay_mode_enum = pgEnum(
    "after_trigger", "before_scheduled", name="delay_mode_enum", create_type=False
)
recipient_type_enum = pgEnum(
    "event_student",
    "event_mentor",
    "event_user",
    "by_role",
    "by_cohort",
    "by_state",
    "specific_users",
    "direction_lead",
    name="recipient_type_enum",
    create_type=False,
)
trigger_regularity_enum = pgEnum(
    "day",
    "week",
    "fortnight",
    "month",
    name="trigger_regularity_enum",
    create_type=False,
)
execution_status_enum = pgEnum(
    "pending",
    "processing",
    "sent",
    "failed",
    name="execution_status_enum",
    create_type=False,
)


def upgrade() -> None:
    conn = op.get_bind()

    for schema in ("iam", "meetings", "surveys", "triggers", "integrations"):
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

    for e in (
        call_status_enum,
        question_type_enum,
        session_status_enum,
        trigger_type_enum,
        action_type_enum,
        delay_mode_enum,
        recipient_type_enum,
        trigger_regularity_enum,
        execution_status_enum,
    ):
        e.create(conn, checkfirst=True)


def downgrade() -> None:
    conn = op.get_bind()

    for e in (
        execution_status_enum,
        trigger_regularity_enum,
        recipient_type_enum,
        delay_mode_enum,
        action_type_enum,
        trigger_type_enum,
        session_status_enum,
        question_type_enum,
        call_status_enum,
    ):
        e.drop(conn, checkfirst=True)

    for schema in ("integrations", "triggers", "surveys", "meetings", "iam"):
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema}"))
