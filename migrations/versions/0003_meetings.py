"""Meetings schema tables: meetings, meeting_users.

Revision ID: 0003_meetings
Revises: 0002_iam
Create Date: 2026-03-22 00:00:02.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

revision: str = "0003_meetings"
down_revision: Union[str, None] = "0002_iam"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

call_status_enum = pgEnum(
    "идёт", "завершён", name="call_status_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meeting_link", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "notion_page_id", sa.String(50), nullable=True, unique=True, index=True
        ),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("topic", sa.String(512), nullable=True),
        sa.Column(
            "mentor_telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column("mentee_telegram_tag", sa.String(255), nullable=True),
        sa.Column("recording_link", sa.String(512), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("action_items", sa.Text, nullable=True),
        sa.Column("project", sa.String(255), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("call_status", call_status_enum, nullable=True),
        sa.Column(
            "student_telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        schema="meetings",
    )
    op.create_table(
        "meeting_users",
        sa.Column(
            "meeting_id",
            sa.Integer,
            sa.ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            primary_key=True,
        ),
        schema="meetings",
    )
    op.create_index(
        "ix_meeting_users_user_id", "meeting_users", ["user_id"], schema="meetings"
    )
    op.create_index(
        "ix_meetings_active_mentor",
        "meetings",
        ["mentor_telegram_id"],
        unique=True,
        postgresql_where=sa.text("call_status = 'идёт'"),
        schema="meetings",
    )


def downgrade() -> None:
    op.drop_table("meeting_users", schema="meetings")
    op.drop_table("meetings", schema="meetings")
