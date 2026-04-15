"""Add UI texts for mentor students archive screen.

Revision ID: 0003_students_archive
Revises: 0002_seed
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_students_archive"
down_revision: Union[str, None] = "0002_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UI_TEXTS = [
    (
        "menu.mentor_students.btn.archive",
        "📋 Прочие менти",
        "Open archive mentees screen",
    ),
    (
        "menu.mentor_students.btn.back_to_active",
        "⬅️ Назад к менти",
        "Back from archive to active mentees",
    ),
    (
        "menu.students.archive.empty",
        "Здесь пока никого нет.",
        "Empty archive mentees list",
    ),
    (
        "menu.students.archive.header",
        "<b>Прочие менти:</b>",
        "Archive mentees list header",
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for key, value, description in UI_TEXTS:
        conn.execute(
            sa.text(
                "INSERT INTO public.ui_texts (key, value, description) "
                "VALUES (:key, :value, :description) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"key": key, "value": value, "description": description},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key, _, _desc in UI_TEXTS:
        conn.execute(
            sa.text("DELETE FROM public.ui_texts WHERE key = :key"),
            {"key": key},
        )
