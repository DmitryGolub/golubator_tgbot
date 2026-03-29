"""Integrations schema tables: cohorts, user_cohorts, stage_transitions.

Revision ID: 0006_integrations
Revises: 0005_triggers
Create Date: 2026-03-22 00:00:05.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_integrations"
down_revision: Union[str, None] = "0005_triggers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cohorts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.UniqueConstraint("type", "value", name="uq_cohort_type_value"),
        schema="integrations",
    )
    op.create_table(
        "user_cohorts",
        sa.Column(
            "user_telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            primary_key=True,
        ),
        sa.Column(
            "cohort_id",
            sa.Integer,
            sa.ForeignKey("integrations.cohorts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="integrations",
    )
    op.create_index(
        "ix_user_cohorts_cohort_id",
        "user_cohorts",
        ["cohort_id"],
        schema="integrations",
    )

    op.create_table(
        "stage_transitions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("cohort_type", sa.String(100), nullable=False),
        sa.Column("old_value", sa.String(255), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="integrations",
    )
    op.create_index(
        "ix_stage_transitions_user_tid",
        "stage_transitions",
        ["user_telegram_id"],
        schema="integrations",
    )
    op.create_index(
        "ix_stage_transitions_created_at",
        "stage_transitions",
        ["created_at"],
        schema="integrations",
    )


def downgrade() -> None:
    op.drop_table("stage_transitions", schema="integrations")
    op.drop_table("user_cohorts", schema="integrations")
    op.drop_table("cohorts", schema="integrations")
