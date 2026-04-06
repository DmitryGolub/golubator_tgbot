"""Update default rating scale from 5 to 10.

Revision ID: 0015_rating_scale_10
Revises: 0014_call_started_at
Create Date: 2026-04-06 00:00:15.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_rating_scale_10"
down_revision: Union[str, None] = "0014_call_started_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE surveys.survey_questions
            SET config = jsonb_set(COALESCE(config, '{}'), '{max}', '10')
            WHERE question_type = 'rating'
              AND (config IS NULL OR (config->>'max')::int = 5)
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE surveys.survey_questions
            SET config = jsonb_set(config, '{max}', '5')
            WHERE question_type = 'rating'
              AND config IS NOT NULL
              AND (config->>'max')::int = 10
            """
        )
    )
