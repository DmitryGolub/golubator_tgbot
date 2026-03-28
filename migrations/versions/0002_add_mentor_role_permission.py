"""Add mentor_role permission and assign to mentor-like roles.

Revision ID: 0002
Revises: init
Create Date: 2026-03-28 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

permissions_t = sa.table(
    "permissions",
    sa.column("id", sa.Integer),
    sa.column("codename", sa.String),
    sa.column("description", sa.String),
    schema="iam",
)
role_perms_t = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("permission_id", sa.Integer),
    schema="iam",
)


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        permissions_t.insert().values(
            codename="mentor_role",
            description="Marker: user has mentor capabilities",
        )
    )

    perm_id = conn.execute(
        sa.text("SELECT id FROM iam.permissions WHERE codename = 'mentor_role'")
    ).scalar_one()

    mentor_roles = ("mentor", "direction_lead", "job_search_lead", "education_lead")
    for role_name in mentor_roles:
        role_id = conn.execute(
            sa.text("SELECT id FROM iam.roles WHERE name = :n"),
            {"n": role_name},
        ).scalar_one()
        conn.execute(
            role_perms_t.insert().values(role_id=role_id, permission_id=perm_id)
        )


def downgrade() -> None:
    conn = op.get_bind()

    perm_id = conn.execute(
        sa.text("SELECT id FROM iam.permissions WHERE codename = 'mentor_role'")
    ).scalar_one()

    conn.execute(
        sa.text("DELETE FROM iam.role_permissions WHERE permission_id = :pid"),
        {"pid": perm_id},
    )
    conn.execute(
        sa.text("DELETE FROM iam.permissions WHERE id = :pid"),
        {"pid": perm_id},
    )
