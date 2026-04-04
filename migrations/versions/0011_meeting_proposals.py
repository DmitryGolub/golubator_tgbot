"""Add meeting proposal/reschedule flow.

Revision ID: 0011_proposals
Revises: 0010_escalation
Create Date: 2026-04-04 00:00:11.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_proposals"
down_revision: Union[str, None] = "0010_escalation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

permissions_t = sa.table(
    "permissions",
    sa.column("codename", sa.String),
    sa.column("description", sa.String),
    schema="iam",
)
roles_t = sa.table(
    "roles",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    schema="iam",
)
role_perms_t = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("permission_id", sa.Integer),
    schema="iam",
)
ui_texts_t = sa.table(
    "ui_texts",
    sa.column("key", sa.String),
    sa.column("value", sa.Text),
    sa.column("description", sa.String),
)


def upgrade() -> None:
    # 1. Create enum type in meetings schema
    op.execute(
        "CREATE TYPE meetings.proposal_status_enum AS ENUM "
        "('ожидает_подтверждения', 'подтверждён')"
    )

    # 2. Add three new columns
    op.add_column(
        "meetings",
        sa.Column(
            "proposal_status",
            sa.Enum(
                "ожидает_подтверждения",
                "подтверждён",
                name="proposal_status_enum",
                schema="meetings",
                create_type=False,
            ),
            nullable=True,
        ),
        schema="meetings",
    )
    op.add_column(
        "meetings",
        sa.Column("proposed_by", sa.BigInteger(), nullable=True),
        schema="meetings",
    )
    op.add_column(
        "meetings",
        sa.Column("original_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        schema="meetings",
    )

    # 3. Backfill existing rows as confirmed (legacy meetings without proposal flow)
    op.execute(
        "UPDATE meetings.meetings SET proposal_status = 'подтверждён' "
        "WHERE proposal_status IS NULL"
    )

    # 4. FK for proposed_by → iam.users.telegram_id
    op.create_foreign_key(
        "fk_meetings_proposed_by_users",
        "meetings",
        "users",
        ["proposed_by"],
        ["telegram_id"],
        source_schema="meetings",
        referent_schema="iam",
        ondelete="SET NULL",
    )

    # 5. Partial index for quick lookup of pending meetings
    op.create_index(
        "ix_meetings_pending",
        "meetings",
        ["proposal_status"],
        schema="meetings",
        postgresql_where=sa.text("proposal_status = 'ожидает_подтверждения'"),
    )

    # 6. Add propose_meetings permission
    op.bulk_insert(
        permissions_t,
        [{"codename": "propose_meetings", "description": "Предложить встречу ментору"}],
    )

    # Assign to student role
    conn = op.get_bind()
    student_role = conn.execute(
        sa.select(roles_t.c.id).where(roles_t.c.name == "student")
    ).fetchone()
    propose_perm = conn.execute(
        sa.select(sa.text("id"))
        .select_from(
            sa.table(
                "permissions",
                sa.column("id", sa.Integer),
                sa.column("codename", sa.String),
                schema="iam",
            )
        )
        .where(sa.text("codename = 'propose_meetings'"))
    ).fetchone()

    if student_role and propose_perm:
        op.bulk_insert(
            role_perms_t,
            [{"role_id": student_role[0], "permission_id": propose_perm[0]}],
        )

    # 7. UI text for menu button
    op.bulk_insert(
        ui_texts_t,
        [
            {
                "key": "menu.btn.propose_meeting",
                "value": "📅 Предложить созвон",
                "description": "Menu: student propose meeting btn",
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM public.ui_texts WHERE key = 'menu.btn.propose_meeting'")

    conn = op.get_bind()
    propose_perm = conn.execute(
        sa.select(sa.text("id"))
        .select_from(
            sa.table(
                "permissions",
                sa.column("id", sa.Integer),
                sa.column("codename", sa.String),
                schema="iam",
            )
        )
        .where(sa.text("codename = 'propose_meetings'"))
    ).fetchone()
    if propose_perm:
        conn.execute(
            sa.delete(role_perms_t).where(
                role_perms_t.c.permission_id == propose_perm[0]
            )
        )
    op.execute("DELETE FROM iam.permissions WHERE codename = 'propose_meetings'")

    op.drop_index("ix_meetings_pending", table_name="meetings", schema="meetings")
    op.drop_constraint(
        "fk_meetings_proposed_by_users",
        "meetings",
        schema="meetings",
        type_="foreignkey",
    )
    op.drop_column("meetings", "original_scheduled_at", schema="meetings")
    op.drop_column("meetings", "proposed_by", schema="meetings")
    op.drop_column("meetings", "proposal_status", schema="meetings")
    op.execute("DROP TYPE meetings.proposal_status_enum")
