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
            WHERE respondent_telegram_id = $1 AND status = 'completed'
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

    async def get_survey_questions(self, template_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM surveys.survey_questions WHERE template_id = $1 ORDER BY position",
            template_id,
        )
        return [dict(r) for r in rows]

    async def get_survey_question_options(self, question_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM surveys.survey_question_options WHERE question_id = $1 ORDER BY position",
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
            "WHERE template_id = $1 AND respondent_telegram_id = $2"
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
