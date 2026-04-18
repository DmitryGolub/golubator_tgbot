"""Deactivate seed trigger rule 'Уведомление о созвоне'.

The direct confirmation message in _finalize_confirmation now carries
date/time, making the broadcast trigger redundant for meeting creation.

Revision ID: 0006_deactivate_meeting_created_notify
Revises: 0005_notion_archived_flag
Create Date: 2026-04-18 19:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006_deactivate_meeting_created_notify"
down_revision: Union[str, None] = "0005_notion_archived_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE triggers.trigger_rules
           SET is_active = false
         WHERE name = 'Уведомление о созвоне'
           AND trigger_type = 'meeting_created'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE triggers.trigger_rules
           SET is_active = true
         WHERE name = 'Уведомление о созвоне'
           AND trigger_type = 'meeting_created'
        """
    )
