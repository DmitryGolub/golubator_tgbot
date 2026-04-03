"""Add escalation fields to survey_sessions.

Revision ID: 0010_escalation
Revises: 0009_alerts
Create Date: 2026-04-03 00:00:10.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_escalation"
down_revision: Union[str, None] = "0009_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "survey_sessions",
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        schema="surveys",
    )
    op.add_column(
        "survey_sessions",
        sa.Column("mentor_notified_at", sa.DateTime(timezone=True), nullable=True),
        schema="surveys",
    )
    op.add_column(
        "survey_sessions",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        schema="surveys",
    )
    op.add_column(
        "survey_sessions",
        sa.Column(
            "is_escalatable",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema="surveys",
    )


def downgrade() -> None:
    op.drop_column("survey_sessions", "is_escalatable", schema="surveys")
    op.drop_column("survey_sessions", "escalated_at", schema="surveys")
    op.drop_column("survey_sessions", "mentor_notified_at", schema="surveys")
    op.drop_column("survey_sessions", "reminder_sent_at", schema="surveys")
