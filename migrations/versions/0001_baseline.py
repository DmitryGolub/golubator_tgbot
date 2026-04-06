"""Baseline DDL: schemas, enums, sequences, all tables.

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-04-06 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Public-schema enums (checkfirst via pgEnum) ────────────────────────

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
    "cohort_changed",
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
    "event_user",
    "by_role",
    "by_cohort",
    "by_state",
    "specific_users",
    "direction_lead",
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
    "pending",
    "processing",
    "sent",
    "failed",
    name="execution_status_enum",
    create_type=False,
)


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Schemas ──────────────────────────────────────────────────────
    for schema in ("iam", "meetings", "surveys", "triggers", "integrations"):
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

    # ── 2. Public-schema enums ──────────────────────────────────────────
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

    # ── 3. Schema-qualified enums (DO $$ EXCEPTION) ─────────────────────
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE iam.lead_source_type_enum AS ENUM ('referral', 'channel'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$"
        )
    )
    lead_source_type_enum = pgEnum(
        "referral",
        "channel",
        name="lead_source_type_enum",
        schema="iam",
        create_type=False,
    )

    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE meetings.proposal_status_enum "
            "AS ENUM ('ожидает_подтверждения', 'подтверждён'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$"
        )
    )
    proposal_status_enum = pgEnum(
        "ожидает_подтверждения",
        "подтверждён",
        name="proposal_status_enum",
        schema="meetings",
        create_type=False,
    )

    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE surveys.alert_type_enum "
            "AS ENUM ('low_score', 'delta_decline', 'cross_mismatch', 'mentor_not_recommend'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$"
        )
    )
    alert_type_enum = pgEnum(
        "low_score",
        "delta_decline",
        "cross_mismatch",
        "mentor_not_recommend",
        name="alert_type_enum",
        schema="surveys",
        create_type=False,
    )

    # ── 4. Sequence ─────────────────────────────────────────────────────
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE SEQUENCE iam.placeholder_user_seq "
            "START WITH -1 INCREMENT BY -1 NO MAXVALUE NO CYCLE; "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$"
        )
    )

    # ── 5. Tables (FK-dependency order) ─────────────────────────────────

    # 5.1 iam.permissions
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("codename", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("description", sa.String(255), nullable=False),
        schema="iam",
    )

    # 5.2 iam.roles
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        schema="iam",
    )

    # 5.3 iam.role_permissions
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

    # 5.4 iam.lead_sources
    op.create_table(
        "lead_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_type", lead_source_type_enum, nullable=False),
        sa.Column("code", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("created_by", sa.BigInteger, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="iam",
    )

    # 5.5 iam.users
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
            "lead_source_id",
            sa.Integer,
            sa.ForeignKey("iam.lead_sources.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        schema="iam",
    )

    # 5.6 iam.mentors
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
        sa.Column("channel_id", sa.BigInteger, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        schema="iam",
    )

    # 5.7 iam.mentees
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

    # 5.8 meetings.meetings (final state — no ix_meetings_active_mentor)
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meeting_link", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("call_started_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("proposal_status", proposal_status_enum, nullable=True),
        sa.Column(
            "proposed_by",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id",
                ondelete="SET NULL",
                name="fk_meetings_proposed_by_users",
            ),
            nullable=True,
        ),
        sa.Column(
            "is_cancelled",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        schema="meetings",
    )
    op.create_index(
        "ix_meetings_pending",
        "meetings",
        ["proposal_status"],
        schema="meetings",
        postgresql_where=sa.text("proposal_status = 'ожидает_подтверждения'"),
    )

    # 5.9 meetings.meeting_users
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

    # 5.10 surveys.survey_templates
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

    # 5.11 surveys.survey_questions
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

    # 5.12 surveys.survey_question_options
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

    # 5.13 surveys.survey_sessions (final state with escalation columns)
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
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mentor_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_escalatable",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
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
    op.create_index(
        "uq_survey_session_no_ctx",
        "survey_sessions",
        ["template_id", "respondent_id"],
        unique=True,
        schema="surveys",
        postgresql_where=sa.text("context_type IS NULL AND context_id IS NULL"),
    )

    # 5.14 surveys.survey_answers
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

    # 5.15 surveys.survey_alerts
    op.create_table(
        "survey_alerts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("alert_type", alert_type_enum, nullable=False),
        sa.Column(
            "session_id",
            sa.Integer,
            sa.ForeignKey("surveys.survey_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.BigInteger,
            sa.ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column(
            "notified",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="surveys",
    )

    # 5.16 triggers.trigger_rules
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
        sa.Column("trigger_config", sa.JSON, nullable=True),
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

    # 5.17 triggers.trigger_executions
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
    op.create_index(
        "uq_trigger_exec_no_event_key",
        "trigger_executions",
        ["rule_id", "recipient_id"],
        unique=True,
        schema="triggers",
        postgresql_where=sa.text("event_key IS NULL"),
    )

    # 5.18 integrations.cohorts
    op.create_table(
        "cohorts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.UniqueConstraint("type", "value", name="uq_cohort_type_value"),
        schema="integrations",
    )

    # 5.19 integrations.user_cohorts
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

    # 5.20 integrations.stage_transitions
    op.create_table(
        "stage_transitions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_telegram_id",
            sa.BigInteger,
            sa.ForeignKey(
                "iam.users.telegram_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("cohort_type", sa.String(100), nullable=False),
        sa.Column("old_value", sa.String(255), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="integrations",
    )
    op.create_index(
        "ix_stage_transitions_user_tid",
        "stage_transitions",
        ["user_telegram_id"],
        schema="integrations",
    )
    op.create_index(
        "ix_stage_transitions_created_at",
        "stage_transitions",
        ["created_at"],
        schema="integrations",
    )

    # 5.21 public.ui_texts
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


def downgrade() -> None:
    conn = op.get_bind()

    # Tables (reverse FK order)
    op.drop_table("ui_texts")
    op.drop_index(
        "ix_stage_transitions_created_at",
        table_name="stage_transitions",
        schema="integrations",
    )
    op.drop_index(
        "ix_stage_transitions_user_tid",
        table_name="stage_transitions",
        schema="integrations",
    )
    op.drop_table("stage_transitions", schema="integrations")
    op.drop_index(
        "ix_user_cohorts_cohort_id",
        table_name="user_cohorts",
        schema="integrations",
    )
    op.drop_table("user_cohorts", schema="integrations")
    op.drop_table("cohorts", schema="integrations")
    op.drop_index(
        "uq_trigger_exec_no_event_key",
        table_name="trigger_executions",
        schema="triggers",
    )
    op.drop_table("trigger_executions", schema="triggers")
    op.drop_table("trigger_rules", schema="triggers")
    op.drop_table("survey_alerts", schema="surveys")
    op.drop_table("survey_answers", schema="surveys")
    op.drop_index(
        "uq_survey_session_no_ctx",
        table_name="survey_sessions",
        schema="surveys",
    )
    op.drop_table("survey_sessions", schema="surveys")
    op.drop_table("survey_question_options", schema="surveys")
    op.drop_table("survey_questions", schema="surveys")
    op.drop_table("survey_templates", schema="surveys")
    op.drop_index(
        "ix_meeting_users_user_id",
        table_name="meeting_users",
        schema="meetings",
    )
    op.drop_table("meeting_users", schema="meetings")
    op.drop_index("ix_meetings_pending", table_name="meetings", schema="meetings")
    op.drop_table("meetings", schema="meetings")
    op.drop_table("mentees", schema="iam")
    op.drop_table("mentors", schema="iam")
    op.drop_table("users", schema="iam")
    op.drop_table("lead_sources", schema="iam")
    op.drop_table("role_permissions", schema="iam")
    op.drop_table("roles", schema="iam")
    op.drop_table("permissions", schema="iam")

    # Sequence
    op.execute(sa.text("DROP SEQUENCE IF EXISTS iam.placeholder_user_seq"))

    # Schema-qualified enums
    op.execute(sa.text("DROP TYPE IF EXISTS surveys.alert_type_enum"))
    op.execute(sa.text("DROP TYPE IF EXISTS meetings.proposal_status_enum"))
    op.execute(sa.text("DROP TYPE IF EXISTS iam.lead_source_type_enum"))

    # Public enums
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

    # Schemas
    for schema in ("integrations", "triggers", "surveys", "meetings", "iam"):
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema}"))
