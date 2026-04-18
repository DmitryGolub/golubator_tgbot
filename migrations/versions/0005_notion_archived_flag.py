"""Notion archived flag for mentors, mentees, meetings.

Revision ID: 0005_notion_archived_flag
Revises: 0004_caldav_pull
Create Date: 2026-04-18 18:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_notion_archived_flag"
down_revision: Union[str, None] = "0004_caldav_pull"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mentors",
        sa.Column(
            "notion_archived",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        schema="iam",
    )
    op.add_column(
        "mentees",
        sa.Column(
            "notion_archived",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        schema="iam",
    )
    op.add_column(
        "meetings",
        sa.Column(
            "notion_archived",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        schema="meetings",
    )


def downgrade() -> None:
    op.drop_column("meetings", "notion_archived", schema="meetings")
    op.drop_column("mentees", "notion_archived", schema="iam")
    op.drop_column("mentors", "notion_archived", schema="iam")
