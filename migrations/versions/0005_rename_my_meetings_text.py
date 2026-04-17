"""Rename menu.btn.my_meetings text from 'Назначенные созвоны' to 'Созвоны'.

Revision ID: 0005_rename_my_meetings
Revises: 0004_fb_enter_text
Create Date: 2026-04-17 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_rename_my_meetings"
down_revision: Union[str, None] = "0004_fb_enter_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE public.ui_texts SET value = :value WHERE key = :key"),
        {"key": "menu.btn.my_meetings", "value": "📅 Созвоны"},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE public.ui_texts SET value = :value WHERE key = :key"),
        {"key": "menu.btn.my_meetings", "value": "📅 Назначенные созвоны"},
    )
