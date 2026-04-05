import asyncpg
from typing import Any


class DBAssertions:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM iam.users WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None

    async def assert_user_exists(self, telegram_id: int) -> dict[str, Any]:
        user = await self.get_user(telegram_id)
        assert user is not None, f"User {telegram_id} not found in DB"
        return user

    async def assert_user_has_role(self, telegram_id: int, role_name: str):
        row = await self._pool.fetchrow(
            """
            SELECT r.name FROM iam.users u
            JOIN iam.roles r ON u.role_id = r.id
            WHERE u.telegram_id = $1
            """,
            telegram_id,
        )
        assert row is not None, f"User {telegram_id} has no role"
        assert row["name"] == role_name, f"Expected role {role_name}, got {row['name']}"

    async def get_meeting(self, meeting_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM meetings.meetings WHERE id = $1", meeting_id
        )
        return dict(row) if row else None

    async def get_meetings_for_mentor(self, mentor_telegram_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM meetings.meetings WHERE mentor_telegram_id = $1 ORDER BY created_at DESC",
            mentor_telegram_id,
        )
        return [dict(r) for r in rows]

    async def assert_meeting_exists(
        self, mentor_id: int, student_id: int
    ) -> dict[str, Any]:
        row = await self._pool.fetchrow(
            """
            SELECT * FROM meetings.meetings
            WHERE mentor_telegram_id = $1 AND student_telegram_id = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            mentor_id,
            student_id,
        )
        assert row is not None, (
            f"Meeting not found for mentor={mentor_id}, student={student_id}"
        )
        return dict(row)

    async def assert_meeting_call_status(self, meeting_id: int, expected_status: str):
        row = await self._pool.fetchrow(
            "SELECT call_status FROM meetings.meetings WHERE id = $1", meeting_id
        )
        assert row is not None, f"Meeting {meeting_id} not found"
        assert row["call_status"] == expected_status

    async def get_survey_session(self, session_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM surveys.survey_sessions WHERE id = $1", session_id
        )
        return dict(row) if row else None

    async def assert_survey_completed(self, user_telegram_id: int) -> dict[str, Any]:
        row = await self._pool.fetchrow(
            """
            SELECT * FROM surveys.survey_sessions
            WHERE respondent_id = $1 AND status = 'completed'
            ORDER BY created_at DESC LIMIT 1
            """,
            user_telegram_id,
        )
        assert row is not None, f"No completed survey for user {user_telegram_id}"
        return dict(row)

    async def get_survey_answers(self, session_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM surveys.survey_answers WHERE session_id = $1",
            session_id,
        )
        return [dict(r) for r in rows]

    async def get_trigger_rule(self, rule_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM triggers.trigger_rules WHERE id = $1", rule_id
        )
        return dict(row) if row else None

    async def get_trigger_executions(self, rule_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM triggers.trigger_executions WHERE rule_id = $1 ORDER BY created_at DESC",
            rule_id,
        )
        return [dict(r) for r in rows]

    async def get_user_cohorts(self, telegram_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            """
            SELECT uc.*, c.type, c.value FROM integrations.user_cohorts uc
            JOIN integrations.cohorts c ON uc.cohort_id = c.id
            WHERE uc.user_telegram_id = $1
            """,
            telegram_id,
        )
        return [dict(r) for r in rows]

    async def get_mentee(self, telegram_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM iam.mentees WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None

    async def get_mentor(self, telegram_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM iam.mentors WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None

    async def get_roles(self) -> list[dict]:
        rows = await self._pool.fetch("SELECT * FROM iam.roles ORDER BY name")
        return [dict(r) for r in rows]

    async def get_role_permissions(self, role_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            """
            SELECT p.* FROM iam.permissions p
            JOIN iam.role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = $1
            """,
            role_id,
        )
        return [dict(r) for r in rows]

    # --- Surveys ---

    async def get_survey_template_by_slug(self, slug: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM surveys.survey_templates WHERE slug = $1", slug
        )
        return dict(row) if row else None

    async def get_survey_template_by_title(self, title: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM surveys.survey_templates WHERE title = $1", title
        )
        return dict(row) if row else None

    async def get_survey_questions(self, template_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM surveys.survey_questions WHERE template_id = $1 ORDER BY sort_order",
            template_id,
        )
        return [dict(r) for r in rows]

    async def get_survey_question_options(self, question_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM surveys.survey_question_options WHERE question_id = $1 ORDER BY sort_order",
            question_id,
        )
        return [dict(r) for r in rows]

    async def count_survey_sessions(
        self,
        template_id: int,
        respondent_id: int,
        context_type: str | None = None,
        context_id: str | None = None,
    ) -> int:
        query = (
            "SELECT COUNT(*) FROM surveys.survey_sessions "
            "WHERE template_id = $1 AND respondent_id = $2"
        )
        params: list[Any] = [template_id, respondent_id]
        if context_type is not None:
            params.append(context_type)
            query += f" AND context_type = ${len(params)}"
        if context_id is not None:
            params.append(context_id)
            query += f" AND context_id = ${len(params)}"
        return await self._pool.fetchval(query, *params)

    # --- Triggers ---

    async def get_trigger_rule_by_name(self, name: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM triggers.trigger_rules WHERE name = $1", name
        )
        return dict(row) if row else None

    async def count_trigger_executions(
        self, rule_id: int, status: str | None = None
    ) -> int:
        if status is not None:
            return await self._pool.fetchval(
                "SELECT COUNT(*) FROM triggers.trigger_executions WHERE rule_id = $1 AND status = $2",
                rule_id,
                status,
            )
        return await self._pool.fetchval(
            "SELECT COUNT(*) FROM triggers.trigger_executions WHERE rule_id = $1",
            rule_id,
        )

    async def assert_meeting_deleted(self, meeting_id: int):
        row = await self._pool.fetchrow(
            "SELECT id FROM meetings.meetings WHERE id = $1", meeting_id
        )
        assert row is None, f"Meeting {meeting_id} should be deleted but still exists"

    async def get_survey_template_with_questions(
        self, template_id: int
    ) -> dict[str, Any] | None:
        template = await self._pool.fetchrow(
            "SELECT * FROM surveys.survey_templates WHERE id = $1", template_id
        )
        if not template:
            return None
        result = dict(template)
        questions = await self.get_survey_questions(template_id)
        for q in questions:
            q["options"] = await self.get_survey_question_options(q["id"])
        result["questions"] = questions
        return result

    async def count_users_with_role(self, role_name: str) -> int:
        return await self._pool.fetchval(
            """
            SELECT COUNT(*) FROM iam.users u
            JOIN iam.roles r ON u.role_id = r.id
            WHERE r.name = $1
            """,
            role_name,
        )

    async def get_role_by_name(self, name: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow("SELECT * FROM iam.roles WHERE name = $1", name)
        return dict(row) if row else None

    # --- Notion sync ---

    async def get_mentor_synced_at(self, telegram_id: int):
        return await self._pool.fetchval(
            "SELECT synced_at FROM iam.mentors WHERE telegram_id = $1", telegram_id
        )

    async def get_mentee_synced_at(self, telegram_id: int):
        return await self._pool.fetchval(
            "SELECT synced_at FROM iam.mentees WHERE telegram_id = $1", telegram_id
        )

    async def get_meeting_notion_page_id(self, meeting_id: int) -> str | None:
        return await self._pool.fetchval(
            "SELECT notion_page_id FROM meetings.meetings WHERE id = $1", meeting_id
        )

    # --- Stage transitions ---

    async def get_stage_transitions(self, telegram_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM integrations.stage_transitions WHERE user_telegram_id = $1 ORDER BY created_at DESC",
            telegram_id,
        )
        return [dict(r) for r in rows]

    # --- Survey alerts ---

    @staticmethod
    def _parse_alert_row(row) -> dict:
        import json as _json

        d = dict(row)
        if isinstance(d.get("details"), str):
            d["details"] = _json.loads(d["details"])
        return d

    async def get_survey_alerts_for_session(self, session_id: int) -> list[dict]:
        """Get all alerts triggered by a survey session."""
        rows = await self._pool.fetch(
            "SELECT * FROM surveys.survey_alerts WHERE session_id = $1 ORDER BY created_at",
            session_id,
        )
        return [self._parse_alert_row(r) for r in rows]

    async def get_survey_alerts_by_type(
        self, session_id: int, alert_type: str
    ) -> list[dict]:
        """Get alerts of specific type for a session."""
        rows = await self._pool.fetch(
            "SELECT * FROM surveys.survey_alerts WHERE session_id = $1 AND alert_type = $2 ORDER BY created_at",
            session_id,
            alert_type,
        )
        return [self._parse_alert_row(r) for r in rows]

    async def get_session_escalation_fields(self, session_id: int) -> dict | None:
        """Get escalation fields (reminder_sent_at, mentor_notified_at, escalated_at, is_escalatable)."""
        row = await self._pool.fetchrow(
            """
            SELECT reminder_sent_at, mentor_notified_at, escalated_at, is_escalatable
            FROM surveys.survey_sessions WHERE id = $1
            """,
            session_id,
        )
        return dict(row) if row else None

    # --- Meeting proposals ---

    async def get_meeting_proposal_status(self, meeting_id: int) -> str | None:
        return await self._pool.fetchval(
            "SELECT proposal_status FROM meetings.meetings WHERE id = $1", meeting_id
        )

    async def assert_meeting_proposal_pending(self, meeting_id: int):
        status = await self.get_meeting_proposal_status(meeting_id)
        assert status == "ожидает_подтверждения", f"Expected pending, got: {status}"

    async def assert_meeting_proposal_confirmed(self, meeting_id: int):
        status = await self.get_meeting_proposal_status(meeting_id)
        assert status == "подтверждён", f"Expected confirmed, got: {status}"

    async def get_meeting_original_scheduled_at(self, meeting_id: int):
        return await self._pool.fetchval(
            "SELECT original_scheduled_at FROM meetings.meetings WHERE id = $1",
            meeting_id,
        )

    async def get_survey_question_id(self, template_id: int, position: int = 0) -> int:
        """Get the question id at the given position (0-based) for a template."""
        return await self._pool.fetchval(
            "SELECT id FROM surveys.survey_questions WHERE template_id = $1 ORDER BY sort_order LIMIT 1 OFFSET $2",
            template_id,
            position,
        )

    async def get_latest_pending_session(self, respondent_id: int) -> dict | None:
        """Get most recent non-completed session for a user."""
        row = await self._pool.fetchrow(
            """
            SELECT * FROM surveys.survey_sessions
            WHERE respondent_id = $1 AND status != 'completed'
            ORDER BY created_at DESC LIMIT 1
            """,
            respondent_id,
        )
        return dict(row) if row else None
