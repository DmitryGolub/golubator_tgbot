"""add RBAC: roles, permissions, role_permissions tables and seed data

Revision ID: add_rbac
Revises: add_tags, add_call_feedback_flow
Create Date: 2026-03-22 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_rbac"
down_revision: Union[str, Sequence[str], None] = ("add_tags", "add_call_feedback_flow")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Predefined permissions: (codename, description)
PERMISSIONS = [
    ("all_permissions", "Полный доступ ко всем функциям"),
    ("manage_users", "Управление пользователями"),
    ("manage_cohorts", "Управление когортами"),
    ("manage_mailings", "Управление рассылками"),
    ("manage_roles", "Управление ролями и пермишенами"),
    ("update_user_role", "Изменение роли пользователя"),
    ("update_user_mentor", "Назначение ментора"),
    ("update_user_cohort", "Назначение когорты"),
    ("update_student_status", "Изменение статуса ученика"),
    ("view_students", "Просмотр учеников"),
    ("manage_meetings", "Создание и удаление созвонов"),
    ("start_call", "Начало созвона"),
    ("end_call", "Завершение созвона"),
    ("give_feedback", "Фидбек по ученику"),
    ("fill_self_review", "Самооценка ментора"),
    ("view_own_meetings", "Просмотр своих созвонов"),
    ("fill_survey", "Заполнить опрос"),
    ("view_own_info", "Информация о себе"),
]

# Roles: (name, display_name, is_mentor, is_student)
ROLES = [
    ("admin", "Админ", False, False),
    ("mentor", "Ментор", True, False),
    ("student", "Студент", False, True),
]

# Role-permission mapping: role_name -> [permission_codenames]
ROLE_PERMISSIONS = {
    "admin": ["all_permissions"],
    "mentor": [
        "update_student_status",
        "view_students",
        "manage_meetings",
        "start_call",
        "end_call",
        "give_feedback",
        "fill_self_review",
        "view_own_meetings",
        "view_own_info",
    ],
    "student": [
        "view_own_meetings",
        "fill_survey",
        "view_own_info",
    ],
}


def upgrade() -> None:
    # 1. Create tables
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("codename", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codename"),
    )
    op.create_index(op.f("ix_permissions_codename"), "permissions", ["codename"])

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("is_mentor", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_student", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"])

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # 2. Add role_id to users (nullable for now)
    op.add_column("users", sa.Column("role_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_role_id", "users", "roles", ["role_id"], ["id"]
    )

    # 3. Seed permissions
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("codename", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions_table,
        [
            {"id": i + 1, "codename": codename, "description": desc}
            for i, (codename, desc) in enumerate(PERMISSIONS)
        ],
    )

    # 4. Seed roles
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("is_mentor", sa.Boolean),
        sa.column("is_student", sa.Boolean),
    )
    op.bulk_insert(
        roles_table,
        [
            {
                "id": i + 1,
                "name": name,
                "display_name": display_name,
                "is_mentor": is_mentor,
                "is_student": is_student,
            }
            for i, (name, display_name, is_mentor, is_student) in enumerate(ROLES)
        ],
    )

    # 5. Build permission id lookup
    perm_id_by_codename = {
        codename: i + 1 for i, (codename, _) in enumerate(PERMISSIONS)
    }
    role_id_by_name = {name: i + 1 for i, (name, _, _, _) in enumerate(ROLES)}

    # 6. Seed role_permissions
    rp_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
    )
    rp_rows = []
    for role_name, perm_codenames in ROLE_PERMISSIONS.items():
        rid = role_id_by_name[role_name]
        for codename in perm_codenames:
            rp_rows.append(
                {"role_id": rid, "permission_id": perm_id_by_codename[codename]}
            )
    op.bulk_insert(rp_table, rp_rows)

    # 7. Populate users.role_id from users.role (enum)
    # admin enum -> roles.id=1, mentor -> 2, student -> 3
    conn = op.get_bind()
    for enum_val, role_id in [("admin", 1), ("mentor", 2), ("student", 3)]:
        conn.execute(
            sa.text("UPDATE users SET role_id = :rid WHERE role = :rval"),
            {"rid": role_id, "rval": enum_val},
        )

    # 8. Make role_id NOT NULL
    op.alter_column("users", "role_id", nullable=False)


def downgrade() -> None:
    op.alter_column("users", "role_id", nullable=True)
    op.drop_constraint("fk_users_role_id", "users", type_="foreignkey")
    op.drop_column("users", "role_id")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
    op.drop_index(op.f("ix_permissions_codename"), table_name="permissions")
    op.drop_table("permissions")
