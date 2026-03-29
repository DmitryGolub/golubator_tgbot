"""IAM schema tables: permissions, roles, users, mentors, mentees.

Revision ID: 0002_iam
Revises: 0001_schemas
Create Date: 2026-03-22 00:00:01.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_iam"
down_revision: Union[str, None] = "0001_schemas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "CREATE SEQUENCE iam.placeholder_user_seq "
            "START WITH -1 INCREMENT BY -1 NO MAXVALUE NO CYCLE"
        )
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("codename", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("description", sa.String(255), nullable=False),
        schema="iam",
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        schema="iam",
    )
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            sa.Integer,
            sa.ForeignKey("iam.roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            sa.Integer,
            sa.ForeignKey("iam.permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="iam",
    )

    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger, primary_key=True),
        sa.Column("username", sa.String(255), unique=True, nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "is_placeholder",
            sa.Boolean,
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("iam.roles.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        schema="iam",
    )

    op.create_table(
        "mentors",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
            unique=True,
            index=True,
        ),
        sa.Column(
            "notion_page_id", sa.String(50), nullable=True, unique=True, index=True
        ),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("about", sa.Text, nullable=True),
        sa.Column("membership_type", sa.String(100), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        schema="iam",
    )

    op.create_table(
        "mentees",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
            unique=True,
            index=True,
        ),
        sa.Column(
            "notion_page_id", sa.String(50), nullable=True, unique=True, index=True
        ),
        sa.Column("doc_name", sa.String(255), nullable=True),
        sa.Column(
            "mentor_id",
            sa.Integer,
            sa.ForeignKey("iam.mentors.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("contract", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("intern", sa.String(255), nullable=True),
        sa.Column("contract_version", sa.Float, nullable=True),
        sa.Column("contract_expires", sa.String(100), nullable=True),
        sa.Column("student_score", sa.Float, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        schema="iam",
    )


def downgrade() -> None:
    op.drop_table("mentees", schema="iam")
    op.drop_table("mentors", schema="iam")
    op.drop_table("users", schema="iam")
    op.drop_table("role_permissions", schema="iam")
    op.drop_table("roles", schema="iam")
    op.drop_table("permissions", schema="iam")
    op.execute(sa.text("DROP SEQUENCE IF EXISTS iam.placeholder_user_seq"))
