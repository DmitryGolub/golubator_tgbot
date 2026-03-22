"""Initial migration — full schema.

Revision ID: init
Revises: None
Create Date: 2026-03-22 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Enums ──────────────────────────────────────────────────────────────────

role_enum = sa.Enum("Админ", "Ментор", "Студент", name="role_enum")
state_enum = sa.Enum("Отбор", "В ожидании", "Обучение", "Поиск работы", "Оффер", name="state_enum")
regularity_enum = sa.Enum("day", "week", "fortnight", "month", name="regularity_enum")
call_status_enum = sa.Enum("идёт", "завершён", name="call_status_enum")
question_type_enum = sa.Enum("text", "rating", "single_choice", "multiple_choice", name="question_type_enum")
session_status_enum = sa.Enum("pending", "in_progress", "completed", name="session_status_enum")
trigger_type_enum = sa.Enum("meeting_created", "call_ended", "periodic_cron", "user_state_changed", "manual", name="trigger_type_enum")
action_type_enum = sa.Enum("send_notification", "send_survey", name="action_type_enum")
delay_mode_enum = sa.Enum("after_trigger", "before_scheduled", name="delay_mode_enum")
recipient_type_enum = sa.Enum("event_student", "event_mentor", "by_role", "by_cohort", "by_state", "by_tag", "specific_users", name="recipient_type_enum")
trigger_regularity_enum = sa.Enum("day", "week", "fortnight", "month", name="trigger_regularity_enum")
execution_status_enum = sa.Enum("pending", "sent", "failed", name="execution_status_enum")


# ── Seed data references ──────────────────────────────────────────────────

permissions_t = sa.table("permissions", sa.column("codename", sa.String), sa.column("description", sa.String))
roles_t = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("display_name", sa.String), sa.column("is_mentor", sa.Boolean), sa.column("is_student", sa.Boolean))
role_perms_t = sa.table("role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer))
templates_t = sa.table("survey_templates", sa.column("id", sa.Integer), sa.column("title", sa.String), sa.column("slug", sa.String), sa.column("description", sa.Text), sa.column("is_active", sa.Boolean))
questions_t = sa.table("survey_questions", sa.column("id", sa.Integer), sa.column("template_id", sa.Integer), sa.column("sort_order", sa.Integer), sa.column("title", sa.String), sa.column("question_type", sa.String), sa.column("is_required", sa.Boolean), sa.column("config", sa.JSON))
options_t = sa.table("survey_question_options", sa.column("id", sa.Integer), sa.column("question_id", sa.Integer), sa.column("sort_order", sa.Integer), sa.column("value", sa.String), sa.column("label", sa.String))
rules_t = sa.table("trigger_rules", sa.column("name", sa.String), sa.column("trigger_type", sa.String), sa.column("action_type", sa.String), sa.column("is_active", sa.Boolean), sa.column("cron_expression", sa.String), sa.column("delay_seconds", sa.Integer), sa.column("delay_mode", sa.String), sa.column("recipient_type", sa.String), sa.column("recipient_config", sa.JSON), sa.column("action_config", sa.JSON))


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Create enums ───────────────────────────────────────────────────
    for e in (role_enum, state_enum, regularity_enum, call_status_enum,
              question_type_enum, session_status_enum, trigger_type_enum,
              action_type_enum, delay_mode_enum, recipient_type_enum,
              trigger_regularity_enum, execution_status_enum):
        e.create(conn, checkfirst=True)

    # ── 2. RBAC tables ────────────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("codename", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("description", sa.String(255), nullable=False),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("is_mentor", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_student", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Integer, sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── 3. Users ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger, primary_key=True, index=True),
        sa.Column("username", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", role_enum, nullable=False, server_default="Студент"),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), nullable=True),
        sa.Column("state", state_enum, nullable=True, server_default="Отбор"),
        sa.Column("mentor_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True),
        sa.Column("notion_page_id", sa.String(50), nullable=True, unique=True, index=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── 4. Tags ───────────────────────────────────────────────────────────
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False, index=True),
    )
    op.create_table(
        "user_tags",
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── 5. Meetings & Calls ──────────────────────────────────────────────
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meeting_link", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "meeting_users",
        sa.Column("meeting_id", sa.Integer, sa.ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "calls",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("meeting_id", sa.Integer, sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("mentor_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("student_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", call_status_enum, nullable=False, server_default=sa.text("'идёт'")),
    )

    # ── 6. Notifications & Rules (legacy mailings) ───────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("regularity", regularity_enum, nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=False),
    )
    op.create_table(
        "state_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_state", state_enum, nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("regularity", regularity_enum, nullable=False),
        sa.Column("author_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=False),
        sa.Column("offset_days", sa.Integer, nullable=True),
    )
    op.create_table(
        "cohort_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cohort_type", sa.String(100), nullable=False),
        sa.Column("cohort_value", sa.String(255), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("regularity", regularity_enum, nullable=False),
        sa.Column("author_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=False),
    )

    # ── 7. Notion cohort cache ───────────────────────────────────────────
    op.create_table(
        "notion_cohort_cache",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_telegram_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("cohort_type", sa.String(100), nullable=False),
        sa.Column("cohort_value", sa.String(255), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_telegram_id", "cohort_type", "cohort_value", name="uq_cohort_cache_user_type_value"),
        sa.Index("ix_cohort_cache_type_value", "cohort_type", "cohort_value"),
    )

    # ── 8. Survey constructor ────────────────────────────────────────────
    op.create_table(
        "survey_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("target_role_id", sa.Integer, sa.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "survey_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("survey_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("question_type", question_type_enum, nullable=False),
        sa.Column("is_required", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("template_id", "sort_order", name="uq_survey_question_order"),
    )
    op.create_table(
        "survey_question_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("survey_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.UniqueConstraint("question_id", "sort_order", name="uq_survey_option_order"),
    )
    op.create_table(
        "survey_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("survey_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("respondent_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("context_type", sa.String(32), nullable=True),
        sa.Column("context_id", sa.String(64), nullable=True),
        sa.Column("status", session_status_enum, nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("template_id", "respondent_id", "context_type", "context_id", name="uq_survey_session_unique"),
    )
    op.create_table(
        "survey_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("survey_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("survey_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value_text", sa.Text, nullable=True),
        sa.Column("value_int", sa.Integer, nullable=True),
        sa.Column("value_choice", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "question_id", name="uq_survey_answer_unique"),
    )

    # ── 9. Trigger system ────────────────────────────────────────────────
    op.create_table(
        "trigger_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger_type", trigger_type_enum, nullable=False),
        sa.Column("action_type", action_type_enum, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("cron_expression", sa.String(64), nullable=True),
        sa.Column("regularity", trigger_regularity_enum, nullable=True),
        sa.Column("time_of_day", sa.Time, nullable=True),
        sa.Column("delay_seconds", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("delay_mode", delay_mode_enum, nullable=False, server_default="after_trigger"),
        sa.Column("recipient_type", recipient_type_enum, nullable=False),
        sa.Column("recipient_config", sa.JSON, nullable=True),
        sa.Column("action_config", sa.JSON, nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "trigger_executions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("rule_id", sa.Integer, sa.ForeignKey("trigger_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=True),
        sa.Column("recipient_id", sa.BigInteger, sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", execution_status_enum, nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rule_id", "event_key", "recipient_id", name="uq_trigger_execution_unique"),
    )

    # ── 10. Seed: permissions ────────────────────────────────────────────
    PERMISSIONS = [
        ("all_permissions", "Полный доступ ко всем функциям"),
        ("manage_users", "Управление пользователями"),
        ("manage_cohorts", "Управление когортами"),
        ("manage_mailings", "Управление рассылками"),
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
    ]
    conn.execute(permissions_t.insert().values([
        {"codename": c, "description": d} for c, d in PERMISSIONS
    ]))

    # ── 10b. Seed: roles ─────────────────────────────────────────────────
    ROLES = [
        {"name": "admin", "display_name": "Админ", "is_mentor": False, "is_student": False},
        {"name": "mentor", "display_name": "Ментор", "is_mentor": True, "is_student": False},
        {"name": "student", "display_name": "Студент", "is_mentor": False, "is_student": True},
    ]
    for role in ROLES:
        conn.execute(roles_t.insert().values(**role))

    # ── 10c. Seed: role_permissions (admin gets all_permissions) ─────────
    admin_role_id = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'admin'")
    ).scalar_one()
    all_perms_id = conn.execute(
        sa.text("SELECT id FROM permissions WHERE codename = 'all_permissions'")
    ).scalar_one()
    conn.execute(role_perms_t.insert().values(role_id=admin_role_id, permission_id=all_perms_id))

    # Mentor default permissions
    mentor_role_id = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'mentor'")
    ).scalar_one()
    mentor_perms = ["view_students", "manage_meetings", "view_own_meetings", "view_own_info", "end_call", "fill_survey", "fill_self_review"]
    for codename in mentor_perms:
        perm_id = conn.execute(
            sa.text("SELECT id FROM permissions WHERE codename = :c"), {"c": codename}
        ).scalar_one()
        conn.execute(role_perms_t.insert().values(role_id=mentor_role_id, permission_id=perm_id))

    # Student default permissions
    student_role_id = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'student'")
    ).scalar_one()
    student_perms = ["view_own_meetings", "view_own_info", "fill_survey"]
    for codename in student_perms:
        perm_id = conn.execute(
            sa.text("SELECT id FROM permissions WHERE codename = :c"), {"c": codename}
        ).scalar_one()
        conn.execute(role_perms_t.insert().values(role_id=student_role_id, permission_id=perm_id))

    # ── 11. Seed: survey templates ───────────────────────────────────────
    TEMPLATES = [
        {
            "slug": "post_call_student", "title": "Опрос ученика после созвона",
            "description": "Заполняется учеником после завершённого созвона с ментором",
            "questions": [
                {"sort_order": 1, "title": "Длительность созвона", "question_type": "single_choice", "is_required": True, "config": None, "options": [
                    {"value": "lt_30", "label": "<30 минут"}, {"value": "30_45", "label": "30-45 минут"},
                    {"value": "45_60", "label": "45-60 минут"}, {"value": "gt_60", "label": ">60 минут"},
                ]},
                {"sort_order": 2, "title": "Стиль общения ментора", "question_type": "rating", "is_required": True, "config": {"min": 1, "max": 5}, "options": []},
                {"sort_order": 3, "title": "Глубина проверки знаний", "question_type": "rating", "is_required": True, "config": {"min": 1, "max": 5}, "options": []},
                {"sort_order": 4, "title": "Насколько ученик понял материал", "question_type": "rating", "is_required": True, "config": {"min": 1, "max": 5}, "options": []},
                {"sort_order": 5, "title": "Комментарий", "question_type": "text", "is_required": False, "config": None, "options": []},
            ],
        },
        {
            "slug": "mentor_feedback", "title": "Фидбек ментора после созвона",
            "description": "Заполняется ментором после завершённого созвона с учеником",
            "questions": [
                {"sort_order": 1, "title": "Готовность ученика", "question_type": "single_choice", "is_required": True, "config": None, "options": [
                    {"value": "not_ready", "label": "Не готов"}, {"value": "bad", "label": "Плохо"},
                    {"value": "ok", "label": "Нормально"}, {"value": "great", "label": "Отлично"},
                ]},
                {"sort_order": 2, "title": "Длительность созвона", "question_type": "single_choice", "is_required": True, "config": None, "options": [
                    {"value": "lt_30", "label": "До 30 минут"}, {"value": "min_30_60", "label": "30-60 минут"},
                    {"value": "min_60_90", "label": "60-90 минут"}, {"value": "ge_90", "label": "90+ минут"},
                ]},
                {"sort_order": 3, "title": "Мотивация ученика", "question_type": "rating", "is_required": True, "config": {"min": 1, "max": 5}, "options": []},
                {"sort_order": 4, "title": "Стадия нейромутации", "question_type": "rating", "is_required": True, "config": {"min": 1, "max": 10}, "options": []},
                {"sort_order": 5, "title": "Комментарий", "question_type": "text", "is_required": False, "config": None, "options": []},
            ],
        },
        {
            "slug": "mentor_self_review", "title": "Ежемесячная самооценка ментора",
            "description": "Заполняется ментором раз в месяц",
            "questions": [
                {"sort_order": 1, "title": "Оцените вашу загрузку", "question_type": "rating", "is_required": True, "config": {"min": 1, "max": 5}, "options": []},
                {"sort_order": 2, "title": "Раздражение тупостью голубя", "question_type": "rating", "is_required": True, "config": {"min": 1, "max": 5}, "options": []},
                {"sort_order": 3, "title": "Средняя нейромутация учеников", "question_type": "rating", "is_required": True, "config": {"min": 1, "max": 10}, "options": []},
                {"sort_order": 4, "title": "Комментарий", "question_type": "text", "is_required": False, "config": None, "options": []},
            ],
        },
    ]

    template_ids = {}
    for tmpl in TEMPLATES:
        r = conn.execute(templates_t.insert().values(title=tmpl["title"], slug=tmpl["slug"], description=tmpl["description"], is_active=True).returning(templates_t.c.id))
        tid = r.scalar_one()
        template_ids[tmpl["slug"]] = tid
        for q in tmpl["questions"]:
            qr = conn.execute(questions_t.insert().values(template_id=tid, sort_order=q["sort_order"], title=q["title"], question_type=q["question_type"], is_required=q["is_required"], config=q["config"]).returning(questions_t.c.id))
            qid = qr.scalar_one()
            for i, opt in enumerate(q["options"]):
                conn.execute(options_t.insert().values(question_id=qid, sort_order=i + 1, value=opt["value"], label=opt["label"]))

    # ── 12. Seed: trigger rules ──────────────────────────────────────────
    NOTIFY_TEXT = "<b>Вам назначен созвон.</b>\nПодробности можно узнать в меню бота."
    REMINDER_TEXT = "<b>Напоминание о созвоне через ~5 минут.</b>\nПодготовьтесь к встрече."

    seed_rules = [
        {"name": "Уведомление о созвоне", "trigger_type": "meeting_created", "action_type": "send_notification", "is_active": True, "delay_seconds": 0, "delay_mode": "after_trigger", "recipient_type": "event_student", "action_config": {"text": NOTIFY_TEXT}},
        {"name": "Напоминание за 5 минут", "trigger_type": "meeting_created", "action_type": "send_notification", "is_active": True, "delay_seconds": 300, "delay_mode": "before_scheduled", "recipient_type": "event_student", "action_config": {"text": REMINDER_TEXT}},
        {"name": "Опрос ученика после созвона", "trigger_type": "call_ended", "action_type": "send_survey", "is_active": True, "delay_seconds": 0, "delay_mode": "after_trigger", "recipient_type": "event_student", "action_config": {"survey_template_id": template_ids["post_call_student"], "survey_title": "Опрос ученика после созвона"}},
        {"name": "Фидбек ментора после созвона", "trigger_type": "call_ended", "action_type": "send_survey", "is_active": True, "delay_seconds": 0, "delay_mode": "after_trigger", "recipient_type": "event_mentor", "action_config": {"survey_template_id": template_ids["mentor_feedback"], "survey_title": "Фидбек ментора после созвона"}},
        {"name": "Ежемесячная самооценка ментора", "trigger_type": "periodic_cron", "action_type": "send_survey", "is_active": True, "cron_expression": "0 9 1 * *", "delay_seconds": 0, "delay_mode": "after_trigger", "recipient_type": "by_role", "recipient_config": {"role_name": "mentor"}, "action_config": {"survey_template_id": template_ids["mentor_self_review"], "survey_title": "Ежемесячная самооценка ментора"}},
    ]
    for rule in seed_rules:
        conn.execute(rules_t.insert().values(**rule))


def downgrade() -> None:
    conn = op.get_bind()
    for t in ("trigger_executions", "trigger_rules", "survey_answers", "survey_sessions",
              "survey_question_options", "survey_questions", "survey_templates",
              "notion_cohort_cache", "cohort_rules", "state_rules", "user_rules",
              "notifications", "calls", "meeting_users", "meetings", "user_tags", "tags",
              "role_permissions", "users", "roles", "permissions"):
        op.drop_table(t)

    for e in (execution_status_enum, trigger_regularity_enum, recipient_type_enum,
              delay_mode_enum, action_type_enum, trigger_type_enum, session_status_enum,
              question_type_enum, call_status_enum, regularity_enum, state_enum, role_enum):
        e.drop(conn, checkfirst=True)
