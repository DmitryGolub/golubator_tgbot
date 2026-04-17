"""Update feedback.enter_text UI copy to mention photo/video attachments.

Revision ID: 0004_fb_enter_text
Revises: 0003_students_archive
Create Date: 2026-04-17 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_fb_enter_text"
down_revision: Union[str, None] = "0003_students_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_VALUE = "Опишите проблему. При желании приложите фото или видео (можно альбомом)."
_OLD_VALUE = "Введите текст обращения:"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE public.ui_texts SET value = :v WHERE key = :k"),
        {"v": _NEW_VALUE, "k": "feedback.enter_text"},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE public.ui_texts SET value = :v WHERE key = :k"),
        {"v": _OLD_VALUE, "k": "feedback.enter_text"},
    )
