"""CalDAV pull: sync_token, ctag, per-link remote tracking.

Revision ID: 0004_caldav_pull
Revises: 0003_caldav
Create Date: 2026-04-18 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_caldav_pull"
down_revision: Union[str, None] = "0003_caldav"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "caldav_accounts",
        sa.Column("sync_token", sa.Text(), nullable=True),
        schema="integrations",
    )
    op.add_column(
        "caldav_accounts",
        sa.Column("ctag", sa.String(length=255), nullable=True),
        schema="integrations",
    )
    op.add_column(
        "caldav_accounts",
        sa.Column("last_pulled_at", sa.DateTime(timezone=True), nullable=True),
        schema="integrations",
    )
    op.add_column(
        "caldav_accounts",
        sa.Column("last_pull_error", sa.Text(), nullable=True),
        schema="integrations",
    )
    op.add_column(
        "caldav_accounts",
        sa.Column("last_pull_error_at", sa.DateTime(timezone=True), nullable=True),
        schema="integrations",
    )

    op.add_column(
        "caldav_event_links",
        sa.Column("remote_last_modified", sa.DateTime(timezone=True), nullable=True),
        schema="integrations",
    )
    op.add_column(
        "caldav_event_links",
        sa.Column("remote_sequence", sa.Integer(), nullable=True),
        schema="integrations",
    )
    op.add_column(
        "caldav_event_links",
        sa.Column("last_pulled_at", sa.DateTime(timezone=True), nullable=True),
        schema="integrations",
    )


def downgrade() -> None:
    op.drop_column("caldav_event_links", "last_pulled_at", schema="integrations")
    op.drop_column("caldav_event_links", "remote_sequence", schema="integrations")
    op.drop_column("caldav_event_links", "remote_last_modified", schema="integrations")

    op.drop_column("caldav_accounts", "last_pull_error_at", schema="integrations")
    op.drop_column("caldav_accounts", "last_pull_error", schema="integrations")
    op.drop_column("caldav_accounts", "last_pulled_at", schema="integrations")
    op.drop_column("caldav_accounts", "ctag", schema="integrations")
    op.drop_column("caldav_accounts", "sync_token", schema="integrations")
