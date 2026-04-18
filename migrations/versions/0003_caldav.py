"""CalDAV sync: accounts + event links.

Revision ID: 0003_caldav
Revises: 0002_seed
Create Date: 2026-04-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

revision: str = "0003_caldav"
down_revision: Union[str, None] = "0002_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


caldav_sync_status_enum = pgEnum(
    "pending",
    "synced",
    "failed",
    name="caldav_sync_status_enum",
    schema="integrations",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    caldav_sync_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "caldav_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "telegram_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("principal_url", sa.String(1024), nullable=True),
        sa.Column("calendar_home_url", sa.String(1024), nullable=True),
        sa.Column("default_calendar_url", sa.String(1024), nullable=True),
        sa.Column("calendar_display_name", sa.String(255), nullable=True),
        sa.Column(
            "sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        schema="integrations",
    )

    op.create_table(
        "caldav_event_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("integrations.caldav_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "meeting_id",
            sa.Integer(),
            sa.ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_uid", sa.String(255), nullable=False),
        sa.Column("event_href", sa.String(1024), nullable=True),
        sa.Column("etag", sa.String(255), nullable=True),
        sa.Column(
            "sequence", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "status",
            caldav_sync_status_enum,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("last_pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.UniqueConstraint(
            "meeting_id", "account_id", name="uq_caldav_event_links_meeting_account"
        ),
        schema="integrations",
    )
    op.create_index(
        "ix_caldav_event_links_account",
        "caldav_event_links",
        ["account_id"],
        schema="integrations",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_caldav_event_links_account",
        table_name="caldav_event_links",
        schema="integrations",
    )
    op.drop_table("caldav_event_links", schema="integrations")
    op.drop_table("caldav_accounts", schema="integrations")

    bind = op.get_bind()
    caldav_sync_status_enum.drop(bind, checkfirst=True)
