"""Add survey_alerts table.

Revision ID: 0009_alerts
Revises: 0008_seed
Create Date: 2026-04-03 00:00:09.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_alerts"
down_revision: Union[str, None] = "0008_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        DO $$ BEGIN
            CREATE TYPE surveys.alert_type_enum
                AS ENUM ('low_score', 'delta_decline', 'cross_mismatch', 'mentor_not_recommend');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
    """)
    )

    alert_type_enum = postgresql.ENUM(
        "low_score",
        "delta_decline",
        "cross_mismatch",
        "mentor_not_recommend",
        name="alert_type_enum",
        schema="surveys",
        create_type=False,
    )

    op.create_table(
        "survey_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "alert_type",
            alert_type_enum,
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("surveys.survey_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.BigInteger(),
            sa.ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "notified",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="surveys",
    )


def downgrade() -> None:
    op.drop_table("survey_alerts", schema="surveys")
    op.execute("DROP TYPE IF EXISTS surveys.alert_type_enum")
