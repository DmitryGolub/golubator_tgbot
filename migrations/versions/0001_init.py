"""Initial migration — full schema.

Revision ID: init
Revises: None
Create Date: 2026-03-22 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

revision: str = "init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Enums ──────────────────────────────────────────────────────────────────

call_status_enum = pgEnum(
    "идёт", "завершён", name="call_status_enum", create_type=False
)
question_type_enum = pgEnum(
    "text",
    "rating",
    "single_choice",
    "multiple_choice",
    name="question_type_enum",
    create_type=False,
)
session_status_enum = pgEnum(
    "pending", "in_progress", "completed", name="session_status_enum", create_type=False
)
trigger_type_enum = pgEnum(
    "meeting_created",
    "call_ended",
    "periodic_cron",
    "user_state_changed",
    "manual",
    name="trigger_type_enum",
    create_type=False,
)
action_type_enum = pgEnum(
    "send_notification", "send_survey", name="action_type_enum", create_type=False
)
delay_mode_enum = pgEnum(
    "after_trigger", "before_scheduled", name="delay_mode_enum", create_type=False
)
recipient_type_enum = pgEnum(
    "event_student",
    "event_mentor",
    "by_role",
    "by_cohort",
    "by_state",
    "specific_users",
    name="recipient_type_enum",
    create_type=False,
)
trigger_regularity_enum = pgEnum(
    "day",
    "week",
    "fortnight",
    "month",
    name="trigger_regularity_enum",
    create_type=False,
)
execution_status_enum = pgEnum(
    "pending", "sent", "failed", name="execution_status_enum", create_type=False
)


# ── Seed data references ──────────────────────────────────────────────────

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
    sa.column("display_name", sa.String),
    schema="iam",
)
role_perms_t = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("permission_id", sa.Integer),
    schema="iam",
)
templates_t = sa.table(
    "survey_templates",
    sa.column("id", sa.Integer),
    sa.column("title", sa.String),
    sa.column("slug", sa.String),
    sa.column("description", sa.Text),
    sa.column("is_active", sa.Boolean),
    schema="surveys",
)
questions_t = sa.table(
    "survey_questions",
    sa.column("id", sa.Integer),
    sa.column("template_id", sa.Integer),
    sa.column("sort_order", sa.Integer),
    sa.column("title", sa.String),
    sa.column("question_type", sa.String),
    sa.column("is_required", sa.Boolean),
    sa.column("config", sa.JSON),
    schema="surveys",
)
options_t = sa.table(
    "survey_question_options",
    sa.column("id", sa.Integer),
    sa.column("question_id", sa.Integer),
    sa.column("sort_order", sa.Integer),
    sa.column("value", sa.String),
    sa.column("label", sa.String),
    schema="surveys",
)
ui_texts_t = sa.table(
    "ui_texts",
    sa.column("key", sa.String),
    sa.column("value", sa.Text),
    sa.column("description", sa.String),
)
rules_t = sa.table(
    "trigger_rules",
    sa.column("name", sa.String),
    sa.column("trigger_type", sa.String),
    sa.column("action_type", sa.String),
    sa.column("is_active", sa.Boolean),
    sa.column("cron_expression", sa.String),
    sa.column("delay_seconds", sa.Integer),
    sa.column("delay_mode", sa.String),
    sa.column("recipient_type", sa.String),
    sa.column("recipient_config", sa.JSON),
    sa.column("action_config", sa.JSON),
    schema="triggers",
)


def upgrade() -> None:
    conn = op.get_bind()

    # ── 0. Create schemas ─────────────────────────────────────────────────
    for schema in ("iam", "meetings", "surveys", "triggers", "integrations"):
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

    # ── 0b. Placeholder user sequence ────────────────────────────────────
    op.execute(
        sa.text(
            "CREATE SEQUENCE iam.placeholder_user_seq "
            "START WITH -1 INCREMENT BY -1 NO MAXVALUE NO CYCLE"
        )
    )

    # ── 1. Create enums ───────────────────────────────────────────────────
    for e in (
        call_status_enum,
        question_type_enum,
        session_status_enum,
        trigger_type_enum,
        action_type_enum,
        delay_mode_enum,
        recipient_type_enum,
        trigger_regularity_enum,
        execution_status_enum,
    ):
        e.create(conn, checkfirst=True)

    # ── 2. RBAC tables ────────────────────────────────────────────────────
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

    # ── 3. Users ──────────────────────────────────────────────────────────
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

    # ── 3b. Mentors ────────────────────────────────────────────────────────
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

    # ── 3c. Mentees ────────────────────────────────────────────────────────
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

    # ── 5. Meetings & Calls ──────────────────────────────────────────────
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meeting_link", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "notion_page_id", sa.String(50), nullable=True, unique=True, index=True
        ),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("topic", sa.String(512), nullable=True),
        sa.Column(
            "mentor_telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column("mentee_telegram_tag", sa.String(255), nullable=True),
        sa.Column("recording_link", sa.String(512), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("action_items", sa.Text, nullable=True),
        sa.Column("project", sa.String(255), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("call_status", call_status_enum, nullable=True),
        sa.Column(
            "student_telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        schema="meetings",
    )
    op.create_table(
        "meeting_users",
        sa.Column(
            "meeting_id",
            sa.Integer,
            sa.ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            primary_key=True,
        ),
        schema="meetings",
    )
    op.create_index(
        "ix_meeting_users_user_id", "meeting_users", ["user_id"], schema="meetings"
    )
    op.create_index(
        "ix_meetings_active_mentor",
        "meetings",
        ["mentor_telegram_id"],
        unique=True,
        postgresql_where=sa.text("call_status = 'идёт'"),
        schema="meetings",
    )

    # ── 6. (Legacy notifications & rules removed) ───────────────────────

    # ── 7. Cohorts ──────────────────────────────────────────────────────
    op.create_table(
        "cohorts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.UniqueConstraint("type", "value", name="uq_cohort_type_value"),
        schema="integrations",
    )
    op.create_table(
        "user_cohorts",
        sa.Column(
            "user_telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            primary_key=True,
        ),
        sa.Column(
            "cohort_id",
            sa.Integer,
            sa.ForeignKey("integrations.cohorts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="integrations",
    )
    op.create_index(
        "ix_user_cohorts_cohort_id",
        "user_cohorts",
        ["cohort_id"],
        schema="integrations",
    )

    # ── 8. Survey constructor ────────────────────────────────────────────
    op.create_table(
        "survey_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "target_role_id",
            sa.Integer,
            sa.ForeignKey("iam.roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_by",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="surveys",
    )
    op.create_table(
        "survey_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("question_type", question_type_enum, nullable=False),
        sa.Column(
            "is_required", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "template_id", "sort_order", name="uq_survey_question_order"
        ),
        schema="surveys",
    )
    op.create_table(
        "survey_question_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.UniqueConstraint("question_id", "sort_order", name="uq_survey_option_order"),
        schema="surveys",
    )
    op.create_table(
        "survey_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "respondent_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("context_type", sa.String(32), nullable=True),
        sa.Column("context_id", sa.String(64), nullable=True),
        sa.Column(
            "status", session_status_enum, nullable=False, server_default="pending"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "template_id",
            "respondent_id",
            "context_type",
            "context_id",
            name="uq_survey_session_unique",
        ),
        schema="surveys",
    )
    op.create_table(
        "survey_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value_text", sa.Text, nullable=True),
        sa.Column("value_int", sa.Integer, nullable=True),
        sa.Column("value_choice", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "session_id", "question_id", name="uq_survey_answer_unique"
        ),
        schema="surveys",
    )

    # ── 9. Trigger system ────────────────────────────────────────────────
    op.create_table(
        "trigger_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger_type", trigger_type_enum, nullable=False),
        sa.Column("action_type", action_type_enum, nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("cron_expression", sa.String(64), nullable=True),
        sa.Column("regularity", trigger_regularity_enum, nullable=True),
        sa.Column("time_of_day", sa.Time, nullable=True),
        sa.Column(
            "delay_seconds", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "delay_mode",
            delay_mode_enum,
            nullable=False,
            server_default="after_trigger",
        ),
        sa.Column("recipient_type", recipient_type_enum, nullable=False),
        sa.Column("recipient_config", sa.JSON, nullable=True),
        sa.Column("action_config", sa.JSON, nullable=False),
        sa.Column(
            "created_by",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="SET NULL", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema="triggers",
    )
    op.create_table(
        "trigger_executions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "rule_id",
            sa.Integer,
            sa.ForeignKey("triggers.trigger_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(128), nullable=True),
        sa.Column(
            "recipient_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "status", execution_status_enum, nullable=False, server_default="pending"
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "rule_id", "event_key", "recipient_id", name="uq_trigger_execution_unique"
        ),
        schema="triggers",
    )
    op.create_index(
        "ix_trigger_exec_pending",
        "trigger_executions",
        ["status", "scheduled_at"],
        schema="triggers",
    )

    # ── 10. UI texts ───────────────────────────────────────────────────
    op.create_table(
        "ui_texts",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── 11. Seed: permissions ────────────────────────────────────────────
    PERMISSIONS = [
        ("all_permissions", "Полный доступ ко всем функциям"),
        ("manage_users", "Управление пользователями"),
        ("manage_cohorts", "Управление когортами"),
        ("manage_roles", "Управление ролями и пермишенами"),
        ("manage_surveys", "Управление шаблонами опросов"),
        ("manage_triggers", "Управление триггерными правилами"),
        ("send_manual", "Ручная и отложенная отправка"),
        ("update_user_role", "Изменение роли пользователя"),
        ("update_user_mentor", "Назначение ментора"),
        ("update_user_cohort", "Назначение когорты"),
        ("update_user_state", "Изменение состояния пользователя"),
        ("view_students", "Просмотр списка учеников"),
        ("manage_meetings", "Управление встречами"),
        ("view_own_meetings", "Просмотр своих встреч"),
        ("view_own_info", "Просмотр своей информации"),
        ("end_call", "Завершение активного созвона"),
        ("fill_survey", "Заполнение опросов"),
        ("fill_self_review", "Заполнение самооценки"),
        ("export_feedback", "Экспорт фидбека в Yandex Sheets"),
        # ── New lead permissions ──
        ("view_direction_students", "Просмотр учеников своего направления"),
        ("receive_direction_notifications", "Получение уведомлений по направлению"),
        ("send_direction_notification", "Отправка уведомлений ученикам направления"),
        ("view_job_search_reports", "Просмотр отчётов по поиску работы"),
        ("view_education_feedback", "Просмотр обратной связи об обучении"),
        ("export_job_search", "Экспорт отчётов по поиску работы"),
        ("export_education_feedback", "Экспорт обратной связи об обучении"),
    ]
    conn.execute(
        permissions_t.insert().values(
            [{"codename": c, "description": d} for c, d in PERMISSIONS]
        )
    )

    # ── 10b. Seed: roles ─────────────────────────────────────────────────
    ROLES = [
        {"name": "admin", "display_name": "Админ"},
        {"name": "mentor", "display_name": "Ментор"},
        {"name": "student", "display_name": "Студент"},
        {"name": "direction_lead", "display_name": "Лид направления"},
        {"name": "job_search_lead", "display_name": "Ответственный за поиск работы"},
        {"name": "education_lead", "display_name": "Ответственный за обучение"},
    ]
    for role in ROLES:
        conn.execute(roles_t.insert().values(**role))

    # ── 10c. Seed: role_permissions (admin gets all_permissions) ─────────
    admin_role_id = conn.execute(
        sa.text("SELECT id FROM iam.roles WHERE name = 'admin'")
    ).scalar_one()
    all_perms_id = conn.execute(
        sa.text("SELECT id FROM iam.permissions WHERE codename = 'all_permissions'")
    ).scalar_one()
    conn.execute(
        role_perms_t.insert().values(role_id=admin_role_id, permission_id=all_perms_id)
    )

    # Mentor default permissions
    mentor_role_id = conn.execute(
        sa.text("SELECT id FROM iam.roles WHERE name = 'mentor'")
    ).scalar_one()
    mentor_perms = [
        "view_students",
        "manage_meetings",
        "view_own_meetings",
        "view_own_info",
        "end_call",
        "fill_survey",
        "fill_self_review",
    ]
    for codename in mentor_perms:
        perm_id = conn.execute(
            sa.text("SELECT id FROM iam.permissions WHERE codename = :c"),
            {"c": codename},
        ).scalar_one()
        conn.execute(
            role_perms_t.insert().values(role_id=mentor_role_id, permission_id=perm_id)
        )

    # Direction lead permissions (mentor perms + direction-specific)
    direction_lead_role_id = conn.execute(
        sa.text("SELECT id FROM iam.roles WHERE name = 'direction_lead'")
    ).scalar_one()
    direction_lead_perms = mentor_perms + [
        "view_direction_students",
        "receive_direction_notifications",
        "send_direction_notification",
    ]
    for codename in direction_lead_perms:
        perm_id = conn.execute(
            sa.text("SELECT id FROM iam.permissions WHERE codename = :c"),
            {"c": codename},
        ).scalar_one()
        conn.execute(
            role_perms_t.insert().values(
                role_id=direction_lead_role_id, permission_id=perm_id
            )
        )

    # Job search lead permissions (mentor perms + job-search-specific)
    job_search_lead_role_id = conn.execute(
        sa.text("SELECT id FROM iam.roles WHERE name = 'job_search_lead'")
    ).scalar_one()
    job_search_lead_perms = mentor_perms + [
        "view_job_search_reports",
        "export_job_search",
        "export_feedback",
    ]
    for codename in job_search_lead_perms:
        perm_id = conn.execute(
            sa.text("SELECT id FROM iam.permissions WHERE codename = :c"),
            {"c": codename},
        ).scalar_one()
        conn.execute(
            role_perms_t.insert().values(
                role_id=job_search_lead_role_id, permission_id=perm_id
            )
        )

    # Education lead permissions (mentor perms + education-specific)
    education_lead_role_id = conn.execute(
        sa.text("SELECT id FROM iam.roles WHERE name = 'education_lead'")
    ).scalar_one()
    education_lead_perms = mentor_perms + [
        "view_education_feedback",
        "export_education_feedback",
        "export_feedback",
    ]
    for codename in education_lead_perms:
        perm_id = conn.execute(
            sa.text("SELECT id FROM iam.permissions WHERE codename = :c"),
            {"c": codename},
        ).scalar_one()
        conn.execute(
            role_perms_t.insert().values(
                role_id=education_lead_role_id, permission_id=perm_id
            )
        )

    # Student default permissions
    student_role_id = conn.execute(
        sa.text("SELECT id FROM iam.roles WHERE name = 'student'")
    ).scalar_one()
    student_perms = ["view_own_meetings", "view_own_info", "fill_survey"]
    for codename in student_perms:
        perm_id = conn.execute(
            sa.text("SELECT id FROM iam.permissions WHERE codename = :c"),
            {"c": codename},
        ).scalar_one()
        conn.execute(
            role_perms_t.insert().values(role_id=student_role_id, permission_id=perm_id)
        )

    # ── 11. Seed: survey templates ───────────────────────────────────────
    TEMPLATES = [
        {
            "slug": "post_call_student",
            "title": "Опрос ученика после созвона",
            "description": "Заполняется учеником после завершённого созвона с ментором",
            "questions": [
                {
                    "sort_order": 1,
                    "title": "Длительность созвона",
                    "question_type": "single_choice",
                    "is_required": True,
                    "config": None,
                    "options": [
                        {"value": "lt_30", "label": "<30 минут"},
                        {"value": "30_45", "label": "30-45 минут"},
                        {"value": "45_60", "label": "45-60 минут"},
                        {"value": "gt_60", "label": ">60 минут"},
                    ],
                },
                {
                    "sort_order": 2,
                    "title": "Стиль общения ментора",
                    "question_type": "rating",
                    "is_required": True,
                    "config": {"min": 1, "max": 5},
                    "options": [],
                },
                {
                    "sort_order": 3,
                    "title": "Глубина проверки знаний",
                    "question_type": "rating",
                    "is_required": True,
                    "config": {"min": 1, "max": 5},
                    "options": [],
                },
                {
                    "sort_order": 4,
                    "title": "Насколько ученик понял материал",
                    "question_type": "rating",
                    "is_required": True,
                    "config": {"min": 1, "max": 5},
                    "options": [],
                },
                {
                    "sort_order": 5,
                    "title": "Комментарий",
                    "question_type": "text",
                    "is_required": False,
                    "config": None,
                    "options": [],
                },
            ],
        },
        {
            "slug": "mentor_feedback",
            "title": "Фидбек ментора после созвона",
            "description": "Заполняется ментором после завершённого созвона с учеником",
            "questions": [
                {
                    "sort_order": 1,
                    "title": "Готовность ученика",
                    "question_type": "single_choice",
                    "is_required": True,
                    "config": None,
                    "options": [
                        {"value": "not_ready", "label": "Не готов"},
                        {"value": "bad", "label": "Плохо"},
                        {"value": "ok", "label": "Нормально"},
                        {"value": "great", "label": "Отлично"},
                    ],
                },
                {
                    "sort_order": 2,
                    "title": "Длительность созвона",
                    "question_type": "single_choice",
                    "is_required": True,
                    "config": None,
                    "options": [
                        {"value": "lt_30", "label": "До 30 минут"},
                        {"value": "min_30_60", "label": "30-60 минут"},
                        {"value": "min_60_90", "label": "60-90 минут"},
                        {"value": "ge_90", "label": "90+ минут"},
                    ],
                },
                {
                    "sort_order": 3,
                    "title": "Мотивация ученика",
                    "question_type": "rating",
                    "is_required": True,
                    "config": {"min": 1, "max": 5},
                    "options": [],
                },
                {
                    "sort_order": 4,
                    "title": "Стадия нейромутации",
                    "question_type": "rating",
                    "is_required": True,
                    "config": {"min": 1, "max": 10},
                    "options": [],
                },
                {
                    "sort_order": 5,
                    "title": "Комментарий",
                    "question_type": "text",
                    "is_required": False,
                    "config": None,
                    "options": [],
                },
            ],
        },
        {
            "slug": "mentor_self_review",
            "title": "Ежемесячная самооценка ментора",
            "description": "Заполняется ментором раз в месяц",
            "questions": [
                {
                    "sort_order": 1,
                    "title": "Оцените вашу загрузку",
                    "question_type": "rating",
                    "is_required": True,
                    "config": {"min": 1, "max": 5},
                    "options": [],
                },
                {
                    "sort_order": 2,
                    "title": "Раздражение тупостью голубя",
                    "question_type": "rating",
                    "is_required": True,
                    "config": {"min": 1, "max": 5},
                    "options": [],
                },
                {
                    "sort_order": 3,
                    "title": "Средняя нейромутация учеников",
                    "question_type": "rating",
                    "is_required": True,
                    "config": {"min": 1, "max": 10},
                    "options": [],
                },
                {
                    "sort_order": 4,
                    "title": "Комментарий",
                    "question_type": "text",
                    "is_required": False,
                    "config": None,
                    "options": [],
                },
            ],
        },
    ]

    template_ids = {}
    for tmpl in TEMPLATES:
        r = conn.execute(
            templates_t.insert()
            .values(
                title=tmpl["title"],
                slug=tmpl["slug"],
                description=tmpl["description"],
                is_active=True,
            )
            .returning(templates_t.c.id)
        )
        tid = r.scalar_one()
        template_ids[tmpl["slug"]] = tid
        for q in tmpl["questions"]:
            qr = conn.execute(
                questions_t.insert()
                .values(
                    template_id=tid,
                    sort_order=q["sort_order"],
                    title=q["title"],
                    question_type=q["question_type"],
                    is_required=q["is_required"],
                    config=q["config"],
                )
                .returning(questions_t.c.id)
            )
            qid = qr.scalar_one()
            for i, opt in enumerate(q["options"]):
                conn.execute(
                    options_t.insert().values(
                        question_id=qid,
                        sort_order=i + 1,
                        value=opt["value"],
                        label=opt["label"],
                    )
                )

    # ── 12. Seed: trigger rules ──────────────────────────────────────────
    NOTIFY_TEXT = "<b>Вам назначен созвон.</b>\nПодробности можно узнать в меню бота."
    REMINDER_TEXT = (
        "<b>Напоминание о созвоне через ~5 минут.</b>\nПодготовьтесь к встрече."
    )

    seed_rules = [
        {
            "name": "Уведомление о созвоне",
            "trigger_type": "meeting_created",
            "action_type": "send_notification",
            "is_active": True,
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_student",
            "action_config": {"text": NOTIFY_TEXT},
        },
        {
            "name": "Напоминание за 5 минут",
            "trigger_type": "meeting_created",
            "action_type": "send_notification",
            "is_active": True,
            "delay_seconds": 300,
            "delay_mode": "before_scheduled",
            "recipient_type": "event_student",
            "action_config": {"text": REMINDER_TEXT},
        },
        {
            "name": "Опрос ученика после созвона",
            "trigger_type": "call_ended",
            "action_type": "send_survey",
            "is_active": True,
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_student",
            "action_config": {
                "survey_template_id": template_ids["post_call_student"],
                "survey_title": "Опрос ученика после созвона",
            },
        },
        {
            "name": "Фидбек ментора после созвона",
            "trigger_type": "call_ended",
            "action_type": "send_survey",
            "is_active": True,
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_mentor",
            "action_config": {
                "survey_template_id": template_ids["mentor_feedback"],
                "survey_title": "Фидбек ментора после созвона",
            },
        },
        {
            "name": "Ежемесячная самооценка ментора",
            "trigger_type": "periodic_cron",
            "action_type": "send_survey",
            "is_active": True,
            "cron_expression": "0 9 1 * *",
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "by_role",
            "recipient_config": {"role_name": "mentor"},
            "action_config": {
                "survey_template_id": template_ids["mentor_self_review"],
                "survey_title": "Ежемесячная самооценка ментора",
            },
        },
    ]
    for rule in seed_rules:
        conn.execute(rules_t.insert().values(**rule))

    # ── 14. Seed: UI texts ──────────────────────────────────────────────
    UI_TEXTS = [
        # ── Menu ──
        ("menu.title", "Список доступных команд", "Main menu title"),
        ("menu.access_denied", "Доступ запрещен.", "Access denied message"),
        ("menu.btn.users", "👥 Пользователи", "Menu button: users"),
        ("menu.btn.cohorts", "📂 Когорты", "Menu button: cohorts"),
        ("menu.btn.surveys", "📝 Опросы", "Menu button: surveys"),
        ("menu.btn.triggers", "⚡ Триггеры", "Menu button: triggers"),
        ("menu.btn.roles", "🛡 Роли", "Menu button: roles"),
        (
            "menu.btn.mentor_stats",
            "📊 Статистика менторов",
            "Menu button: mentor stats",
        ),
        (
            "menu.btn.export_feedback",
            "📤 Экспорт фидбека",
            "Menu button: export feedback",
        ),
        ("menu.btn.students", "🎓 Ученики", "Menu button: students (mentor)"),
        ("menu.btn.meetings", "📅 Созвоны", "Menu button: meetings (mentor)"),
        ("menu.btn.my_info", "ℹ️ Обо мне", "Menu button: my info (mentor)"),
        (
            "menu.btn.my_meetings",
            "📅 Назначенные созвоны",
            "Menu button: my meetings (student)",
        ),
        (
            "menu.btn.my_info_student",
            "ℹ️ Информация обо мне",
            "Menu button: my info (student)",
        ),
        ("menu.back", "⬅️ Назад к меню", "Back to menu button"),
        # ── Submenu titles ──
        ("menu.users.title", "👥 Меню Пользователей", "Users submenu title"),
        ("menu.cohorts.title", "📂 Меню Когорт", "Cohorts submenu title"),
        ("menu.meetings.title", "📅 Созвоны:", "Meetings submenu title"),
        ("menu.students.title", "🎓 Ученики:", "Students submenu title"),
        # ── Mentor students ──
        ("menu.students.empty", "Список учеников пуст.", "Empty students list"),
        ("menu.students.header", "<b>Мои ученики:</b>", "Students list header"),
        (
            "menu.mentor_students.btn.list",
            "Список учеников",
            "Mentor: students list btn",
        ),
        (
            "menu.mentor_students.btn.update",
            "Изменить статус ученика",
            "Mentor: update student btn",
        ),
        # ── Mentor meetings ──
        (
            "menu.mentor_meetings.btn.list",
            "Список созвонов",
            "Mentor: meetings list btn",
        ),
        (
            "menu.mentor_meetings.btn.create",
            "Добавить созвон",
            "Mentor: create meeting btn",
        ),
        (
            "menu.mentor_meetings.btn.end_call",
            "Завершить активный созвон",
            "Mentor: end call btn",
        ),
        (
            "menu.mentor_meetings.btn.feedback",
            "Заполнить фидбек",
            "Mentor: fill feedback btn",
        ),
        # ── Call end messages ──
        ("menu.no_active_call", "У вас нет активного созвона.", "No active call"),
        (
            "menu.call_ended.no_meeting",
            "✅ Активный созвон завершён.\nНачало: {start}\nКонец: {end}",
            "Call ended (no meeting)",
        ),
        (
            "menu.call_ended.with_meeting",
            "✅ Созвон по встрече #{id} завершён.\nНачало: {start}\nКонец: {end}\n\nТеперь можно заполнить фидбек.",
            "Call ended (with meeting)",
        ),
        # ── Profile ──
        ("menu.not_found", "Профиль не найден.", "Profile not found"),
        ("menu.me.title", "<b>Моя информация:</b>", "Profile title"),
        ("menu.mentor_me.btn.stats", "Моя статистика", "Mentor: my stats btn"),
        # ── Start ──
        (
            "start.welcome",
            "<b>Привет, {name}!</b>\n\nЯ буду напоминать вам о занятиях и присылать полезную информацию.\nЧерез команду <b>/menu</b> можно открыть главное меню, посмотреть свои данные и доступные действия.\n\nЕсли что-то не работает — напишите куратору.",
            "Welcome message",
        ),
        # ── Users ──
        ("user.btn.list", "Список пользователей", "Users: list btn"),
        ("user.btn.update", "Изменить пользователя", "Users: update btn"),
        ("user.btn.update_status", "🔄 Обновить статус", "Users: update status btn"),
        ("user.btn.update_role", "🛡 Обновить роль", "Users: update role btn"),
        ("user.btn.update_mentor", "👨‍🏫 Обновить ментора", "Users: update mentor btn"),
        (
            "user.btn.update_student_status",
            "🔄 Обновить статус ученика",
            "Users: update student status btn",
        ),
        ("user.list.header", "<b>Список пользователей:</b>", "Users list header"),
        ("user.list.empty", "<b>Список пользователей пуст.</b>", "Users list empty"),
        ("user.update.what", "Что вы хотите обновить?", "Update user: choose param"),
        ("user.update.access_denied", "Доступ запрещен.", "Update user: access denied"),
        (
            "user.update.success",
            "Пользователь {name} @{username}\n{param} обновлено на: {value}",
            "Update user: success",
        ),
        # ── Cohorts ──
        ("cohort.btn.types", "Типы когорт", "Cohorts: types list btn"),
        ("cohort.btn.create_type", "Создать тип когорты", "Cohorts: create type btn"),
        ("cohort.types.header", "<b>Типы когорт:</b>", "Cohorts list header"),
        (
            "cohort.not_configured",
            "Notion не настроен (NOTION_TOKEN / NOTION_DATABASE_ID).",
            "Notion not configured",
        ),
        (
            "cohort.not_found",
            "Типы когорт не найдены в Notion.",
            "No cohort types found",
        ),
        # ── Mailings ──
        ("mailings.btn.list", "Список рассылок", "Mailings: list btn"),
        ("mailings.btn.add", "Добавить рассылку", "Mailings: add btn"),
        ("mailings.btn.delete", "Удалить рассылку", "Mailings: delete btn"),
        ("mailings.list.header", "<b>Список рассылок:</b>", "Mailings list header"),
        ("mailings.list.empty", "<b>Список рассылок пуст.</b>", "Mailings list empty"),
        ("mailings.choose_type", "Выберите тип рассылки:", "Choose mailing type"),
        ("mailings.enter_title", "Введите название рассылки:", "Enter mailing title"),
        # ── Meetings ──
        ("meeting.list.empty", "Список созвонов пуст.", "Meetings list empty"),
        ("meeting.list.header", "<b>Мои созвоны:</b>", "Meetings list header"),
        ("meeting.error.not_found", "Созвон не найден.", "Meeting not found"),
        (
            "meeting.error.no_access",
            "У вас нет доступа к этому созвону.",
            "Meeting: no access",
        ),
        (
            "meeting.error.already_completed",
            "Этот созвон уже завершён.",
            "Meeting already completed",
        ),
        (
            "meeting.error.active_exists",
            "У вас уже есть активный созвон. Сначала завершите его через кнопку или команду /end_call.",
            "Active call exists",
        ),
        # ── Mentor stats ──
        (
            "mentor_stats.header",
            "<b>Статистика ментора: {name}</b>",
            "Mentor stats header",
        ),
        ("mentor_stats.no_scores", "Оценок пока нет.", "No scores yet"),
        ("mentor_stats.not_found", "Ментор не найден.", "Mentor not found"),
        (
            "mentor_stats.select",
            "Выберите ментора для просмотра статистики:",
            "Select mentor",
        ),
        ("mentor_stats.no_mentors", "Менторов не найдено.", "No mentors found"),
        # ── Export ──
        (
            "export.not_configured",
            "Экспорт не настроен: проверьте YANDEX_SHEETS_* переменные.",
            "Export not configured",
        ),
        (
            "export.running",
            "⏳ Экспорт фидбека запущен, подождите...",
            "Export running",
        ),
        (
            "export.upload_error",
            "Не удалось загрузить файл в Яндекс Таблицу.",
            "Export upload error",
        ),
        (
            "export.internal_error",
            "Внутренняя ошибка экспорта.",
            "Export internal error",
        ),
        (
            "export.success",
            "✅ Экспорт завершён.\n\nСтрок: <b>{rows}</b>\nФайл: <b>{file}</b>\nЛист: <b>{sheet}</b>",
            "Export success",
        ),
        # ── Triggers ──
        ("trigger.btn.create", "Создать правило", "Triggers: create btn"),
        ("trigger.btn.list", "Список правил", "Triggers: list btn"),
        ("trigger.btn.manual_send", "Отправить вручную", "Triggers: manual send btn"),
        ("trigger.menu.title", "Управление триггерами", "Triggers menu title"),
        ("trigger.no_rules", "Нет правил", "No trigger rules"),
        ("trigger.list.header", "Правила:", "Trigger rules header"),
        ("trigger.rule_not_found", "Правило не найдено", "Trigger rule not found"),
        ("trigger.deleted", "Правило удалено", "Trigger rule deleted"),
        # ── Trigger labels ──
        (
            "trigger.type.meeting_created",
            "Создание встречи",
            "Trigger type: meeting created",
        ),
        ("trigger.type.call_ended", "Завершение созвона", "Trigger type: call ended"),
        ("trigger.type.periodic_cron", "По расписанию", "Trigger type: periodic cron"),
        (
            "trigger.type.user_state_changed",
            "Смена статуса",
            "Trigger type: user state changed",
        ),
        ("trigger.type.manual", "Ручной", "Trigger type: manual"),
        (
            "trigger.action.send_notification",
            "Отправить уведомление",
            "Action: send notification",
        ),
        ("trigger.action.send_survey", "Отправить опрос", "Action: send survey"),
        (
            "trigger.recipient.event_student",
            "Ученик из события",
            "Recipient: event student",
        ),
        (
            "trigger.recipient.event_mentor",
            "Ментор из события",
            "Recipient: event mentor",
        ),
        ("trigger.recipient.by_role", "По роли", "Recipient: by role"),
        ("trigger.recipient.by_cohort", "По когорте", "Recipient: by cohort"),
        ("trigger.recipient.by_state", "По статусу", "Recipient: by state"),
        (
            "trigger.recipient.specific_users",
            "Конкретные пользователи",
            "Recipient: specific users",
        ),
        # ── Surveys ──
        ("survey.btn.create", "Создать опрос", "Surveys: create btn"),
        ("survey.btn.list", "Список опросов", "Surveys: list btn"),
        ("survey.btn.results", "Результаты", "Surveys: results btn"),
        ("survey.menu.title", "Конструктор опросов", "Surveys menu title"),
        ("survey.no_surveys", "Нет созданных опросов", "No surveys"),
        ("survey.not_found", "Опрос не найден", "Survey not found"),
        ("survey.deleted", "Опрос удалён", "Survey deleted"),
        ("survey.type.text", "Текст", "Question type: text"),
        ("survey.type.rating", "Рейтинг (число)", "Question type: rating"),
        (
            "survey.type.single_choice",
            "Одиночный выбор",
            "Question type: single choice",
        ),
        (
            "survey.type.multiple_choice",
            "Множественный выбор",
            "Question type: multiple choice",
        ),
        # ── Dynamic surveys ──
        ("dynamic_survey.not_found", "Опрос не найден", "Dynamic survey not found"),
        (
            "dynamic_survey.already_completed",
            "Вы уже заполнили этот опрос",
            "Survey already completed",
        ),
        ("dynamic_survey.cancelled", "Опрос отменён.", "Survey cancelled"),
        # ── RBAC ──
        ("rbac.btn.create_role", "➕ Создать роль", "RBAC: create role btn"),
        ("rbac.btn.back_to_roles", "⬅️ К списку ролей", "RBAC: back to roles btn"),
        (
            "rbac.btn.manage_perms",
            "🔑 Управление пермишенами",
            "RBAC: manage perms btn",
        ),
        ("rbac.btn.delete_role", "🗑 Удалить роль", "RBAC: delete role btn"),
        ("rbac.menu.title", "<b>Управление ролями</b>", "RBAC menu title"),
        ("rbac.role_not_found", "Роль не найдена.", "Role not found"),
        ("rbac.confirm_delete", "Удалить роль <b>{name}</b>?", "Confirm role deletion"),
        (
            "rbac.users_cannot_delete",
            "Нельзя удалить роль, к которой привязаны пользователи.",
            "Cannot delete role with users",
        ),
        # ── Lead menu ──
        (
            "menu.btn.direction_students",
            "🎯 Ученики направления",
            "Menu button: direction students",
        ),
        (
            "menu.btn.send_direction",
            "📨 Рассылка по направлению",
            "Menu button: send direction notification",
        ),
        (
            "menu.btn.job_search_reports",
            "💼 Отчёты: поиск работы",
            "Menu button: job search reports",
        ),
        (
            "menu.btn.education_feedback",
            "📚 Обратная связь: обучение",
            "Menu button: education feedback",
        ),
        # ── Direction assignment ──
        (
            "direction.choose_cohorts",
            "Выберите направления (когорты Category) для лида:",
            "Direction assignment: choose cohorts prompt",
        ),
        (
            "direction.saved",
            "✅ Направления сохранены.",
            "Direction assignment: saved confirmation",
        ),
        (
            "direction.no_categories",
            "Нет доступных направлений (когорт типа Category).",
            "Direction assignment: no categories found",
        ),
        # ── Job search reports ──
        (
            "job_search.title",
            "💼 Отчёты по поиску работы",
            "Job search report: title",
        ),
        (
            "job_search.no_data",
            "Нет данных за выбранный период.",
            "Job search report: no data",
        ),
        (
            "job_search.choose_period",
            "Выберите период:",
            "Job search report: choose period",
        ),
        # ── Education feedback ──
        (
            "education.title",
            "📚 Обратная связь об обучении",
            "Education feedback: title",
        ),
        (
            "education.no_data",
            "Нет данных за выбранный период.",
            "Education feedback: no data",
        ),
        (
            "education.choose_period",
            "Выберите период:",
            "Education feedback: choose period",
        ),
        # ── Common ──
        ("common.cancel", "❌ Отмена", "Cancel button"),
        ("common.confirm.yes", "✅ Да, удалить", "Confirm: yes"),
        ("common.confirm.no", "❌ Отмена", "Confirm: no"),
        ("common.loading", "⏳ Загрузка...", "Loading indicator"),
    ]
    for key, value, description in UI_TEXTS:
        conn.execute(
            ui_texts_t.insert().values(key=key, value=value, description=description)
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Drop tables in reverse dependency order
    op.drop_table("ui_texts")
    op.drop_table("trigger_executions", schema="triggers")
    op.drop_table("trigger_rules", schema="triggers")
    op.drop_table("survey_answers", schema="surveys")
    op.drop_table("survey_sessions", schema="surveys")
    op.drop_table("survey_question_options", schema="surveys")
    op.drop_table("survey_questions", schema="surveys")
    op.drop_table("survey_templates", schema="surveys")
    op.drop_table("user_cohorts", schema="integrations")
    op.drop_table("cohorts", schema="integrations")
    op.drop_table("meeting_users", schema="meetings")
    op.drop_table("meetings", schema="meetings")
    op.drop_table("mentees", schema="iam")
    op.drop_table("mentors", schema="iam")
    op.drop_table("role_permissions", schema="iam")
    op.drop_table("users", schema="iam")
    op.execute(sa.text("DROP SEQUENCE IF EXISTS iam.placeholder_user_seq"))
    op.drop_table("roles", schema="iam")
    op.drop_table("permissions", schema="iam")

    for e in (
        execution_status_enum,
        trigger_regularity_enum,
        recipient_type_enum,
        delay_mode_enum,
        action_type_enum,
        trigger_type_enum,
        session_status_enum,
        question_type_enum,
        call_status_enum,
    ):
        e.drop(conn, checkfirst=True)

    for schema in ("integrations", "triggers", "surveys", "meetings", "iam"):
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema}"))
