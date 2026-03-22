"""Migrate cohorts from PostgreSQL to Notion: add notion_page_id, notion_cohort_cache,
refactor cohort_rules, drop cohorts table.

Revision ID: notion_cohorts
Revises: add_rbac
Create Date: 2026-03-22 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "notion_cohorts"
down_revision: Union[str, Sequence[str], None] = "add_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add notion_page_id to users, drop cohort_id FK
    op.add_column(
        "users",
        sa.Column("notion_page_id", sa.String(50), nullable=True, unique=True),
    )
    op.create_index("ix_users_notion_page_id", "users", ["notion_page_id"])

    op.drop_constraint("users_cohort_id_fkey", "users", type_="foreignkey")
    op.drop_column("users", "cohort_id")

    # 2. Create notion_cohort_cache table
    op.create_table(
        "notion_cohort_cache",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_telegram_id",
            sa.BigInteger,
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("cohort_type", sa.String(100), nullable=False),
        sa.Column("cohort_value", sa.String(255), nullable=False),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_telegram_id",
            "cohort_type",
            "cohort_value",
            name="uq_cohort_cache_user_type_value",
        ),
        sa.Index("ix_cohort_cache_type_value", "cohort_type", "cohort_value"),
    )

    # 3. Refactor cohort_rules: drop cohort_id FK, add cohort_type + cohort_value
    op.add_column(
        "cohort_rules",
        sa.Column("cohort_type", sa.String(100), nullable=True),
    )
    op.add_column(
        "cohort_rules",
        sa.Column("cohort_value", sa.String(255), nullable=True),
    )

    # Migrate existing cohort_rules: set cohort_type='legacy', cohort_value=cohort_id
    op.execute(
        "UPDATE cohort_rules SET cohort_type = 'legacy', "
        "cohort_value = CAST(cohort_id AS VARCHAR) WHERE cohort_type IS NULL"
    )

    op.alter_column("cohort_rules", "cohort_type", nullable=False)
    op.alter_column("cohort_rules", "cohort_value", nullable=False)

    op.drop_constraint("cohort_rules_cohort_id_fkey", "cohort_rules", type_="foreignkey")
    op.drop_column("cohort_rules", "cohort_id")

    # 4. Drop cohorts table
    op.drop_table("cohorts")


def downgrade() -> None:
    # Recreate cohorts table
    op.create_table(
        "cohorts",
        sa.Column("id", sa.BigInteger, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
    )

    # Restore cohort_rules.cohort_id
    op.add_column(
        "cohort_rules",
        sa.Column("cohort_id", sa.BigInteger, nullable=True),
    )
    op.create_foreign_key(
        "cohort_rules_cohort_id_fkey",
        "cohort_rules",
        "cohorts",
        ["cohort_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("cohort_rules", "cohort_value")
    op.drop_column("cohort_rules", "cohort_type")

    # Drop notion_cohort_cache
    op.drop_table("notion_cohort_cache")

    # Restore users.cohort_id
    op.add_column(
        "users",
        sa.Column("cohort_id", sa.Integer, nullable=True),
    )
    op.create_foreign_key(
        "users_cohort_id_fkey",
        "users",
        "cohorts",
        ["cohort_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index("ix_users_notion_page_id", "users")
    op.drop_column("users", "notion_page_id")
