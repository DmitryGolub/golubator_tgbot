import asyncpg
from typing import Any


class E2ESetup:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    _redis_url: str | None = None

    async def set_user_role(self, telegram_id: int, role_name: str):
        """Assign a role to a user and flush Redis permission cache."""
        await self._pool.execute(
            """
            UPDATE iam.users SET role_id = (
                SELECT id FROM iam.roles WHERE name = $1
            ) WHERE telegram_id = $2
            """,
            role_name,
            telegram_id,
        )
        # Flush Redis to invalidate permission cache
        if self._redis_url:
            await self.flush_redis(self._redis_url)

    async def ensure_user_record(self, telegram_id: int, name: str = "E2E User"):
        """Create a User record if it doesn't exist (FK dependency for mentors/mentees)."""
        await self._pool.execute(
            """INSERT INTO iam.users (telegram_id, name, is_placeholder)
               VALUES ($1, $2, false) ON CONFLICT (telegram_id) DO NOTHING""",
            telegram_id,
            name,
        )

    async def ensure_mentor_record(self, telegram_id: int):
        """Create a Mentor record if it doesn't exist."""
        await self.ensure_user_record(telegram_id)
        existing = await self._pool.fetchrow(
            "SELECT id FROM iam.mentors WHERE telegram_id = $1", telegram_id
        )
        if not existing:
            await self._pool.execute(
                "INSERT INTO iam.mentors (telegram_id) VALUES ($1)", telegram_id
            )

    async def ensure_mentee_record(
        self, telegram_id: int, mentor_telegram_id: int | None = None
    ):
        """Create a Mentee record if it doesn't exist."""
        await self.ensure_user_record(telegram_id)
        if mentor_telegram_id:
            await self.ensure_user_record(mentor_telegram_id)
            await self.ensure_mentor_record(mentor_telegram_id)
        existing = await self._pool.fetchrow(
            "SELECT id FROM iam.mentees WHERE telegram_id = $1", telegram_id
        )
        if not existing:
            mentor_id = None
            if mentor_telegram_id:
                row = await self._pool.fetchrow(
                    "SELECT id FROM iam.mentors WHERE telegram_id = $1",
                    mentor_telegram_id,
                )
                mentor_id = row["id"] if row else None
            await self._pool.execute(
                "INSERT INTO iam.mentees (telegram_id, mentor_id) VALUES ($1, $2)",
                telegram_id,
                mentor_id,
            )

    # Tables preserved between test modules (seed data from migrations)
    _PRESERVE_TABLES = {
        ("iam", "roles"),
        ("iam", "permissions"),
        ("iam", "role_permissions"),
        ("public", "ui_texts"),
    }

    async def truncate_all(self):
        """Truncate all tables between test suites, preserving seed data."""
        schemas = ["triggers", "surveys", "meetings", "integrations", "iam", "public"]
        for schema in schemas:
            tables = await self._pool.fetch(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = $1 AND tablename != 'alembic_version'
                """,
                schema,
            )
            for table in tables:
                if (schema, table["tablename"]) in self._PRESERVE_TABLES:
                    continue
                await self._pool.execute(
                    f'TRUNCATE TABLE {schema}."{table["tablename"]}" CASCADE'
                )

    async def flush_redis(self, redis_url: str):
        """Flush Redis (FSM state, permission cache)."""
        import redis.asyncio as aioredis

        r = aioredis.from_url(redis_url)
        await r.flushall()
        await r.aclose()

    # --- Surveys ---

    async def create_survey_template(
        self, title: str, slug: str, questions: list[dict[str, Any]]
    ) -> int:
        """Create survey template + questions + options directly in DB.

        Returns template_id.
        questions: [{"title": ..., "type": "text"|"rating"|"single_choice"|"multiple_choice",
                     "config": {...}, "options": [{"value": ..., "label": ...}]}]
        """
        import json

        # Clean up from previous failed runs to avoid UniqueViolationError
        await self._pool.execute(
            "DELETE FROM surveys.survey_templates WHERE slug = $1", slug
        )

        template_id = await self._pool.fetchval(
            """
            INSERT INTO surveys.survey_templates (title, slug, is_active)
            VALUES ($1, $2, true)
            RETURNING id
            """,
            title,
            slug,
        )
        for pos, q in enumerate(questions, start=1):
            config_json = json.dumps(q.get("config", {}))
            question_id = await self._pool.fetchval(
                """
                INSERT INTO surveys.survey_questions
                    (template_id, title, question_type, sort_order, is_required, config)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING id
                """,
                template_id,
                q["title"],
                q["type"],
                pos,
                q.get("is_required", True),
                config_json,
            )
            for opt_pos, opt in enumerate(q.get("options", []), start=1):
                await self._pool.execute(
                    """
                    INSERT INTO surveys.survey_question_options
                        (question_id, value, label, sort_order)
                    VALUES ($1, $2, $3, $4)
                    """,
                    question_id,
                    opt["value"],
                    opt["label"],
                    opt_pos,
                )
        return template_id

    async def create_survey_session(
        self,
        template_id: int,
        respondent_id: int,
        context_type: str = "test",
        context_id: str = "e2e",
    ) -> int:
        """Create a pending survey session directly in DB. Returns session_id."""
        return await self._pool.fetchval(
            """
            INSERT INTO surveys.survey_sessions
                (template_id, respondent_id, context_type, context_id, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING id
            """,
            template_id,
            respondent_id,
            context_type,
            context_id,
        )

    async def ensure_role_permission(self, role_name: str, permission_name: str):
        """Ensure a role has a specific permission in role_permissions."""
        await self._pool.execute(
            """
            INSERT INTO iam.role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM iam.roles r, iam.permissions p
            WHERE r.name = $1 AND p.codename = $2
            ON CONFLICT DO NOTHING
            """,
            role_name,
            permission_name,
        )

    async def add_fake_mentor(self, telegram_id: int, name: str):
        """Create a non-placeholder user with role=mentor and a mentor record."""
        await self._pool.execute(
            """
            INSERT INTO iam.users (telegram_id, name, role_id, is_placeholder)
            VALUES ($1, $2, (SELECT id FROM iam.roles WHERE name = 'mentor'), false)
            ON CONFLICT (telegram_id) DO UPDATE SET
                role_id = (SELECT id FROM iam.roles WHERE name = 'mentor'),
                is_placeholder = false
            """,
            telegram_id,
            name,
        )
        await self._pool.execute(
            "INSERT INTO iam.mentors (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING",
            telegram_id,
        )

    # --- Cohorts ---

    async def ensure_user_cohort(
        self, telegram_id: int, cohort_type: str, cohort_value: str
    ):
        """Ensure user has a specific cohort assignment."""
        cohort_id = await self._pool.fetchval(
            "SELECT id FROM integrations.cohorts WHERE type = $1 AND value = $2",
            cohort_type,
            cohort_value,
        )
        if cohort_id is None:
            cohort_id = await self._pool.fetchval(
                "INSERT INTO integrations.cohorts (type, value) VALUES ($1, $2) RETURNING id",
                cohort_type,
                cohort_value,
            )
        existing = await self._pool.fetchval(
            """
            SELECT cohort_id FROM integrations.user_cohorts
            WHERE user_telegram_id = $1 AND cohort_id IN (
                SELECT id FROM integrations.cohorts WHERE type = $2
            )
            """,
            telegram_id,
            cohort_type,
        )
        if existing:
            await self._pool.execute(
                """
                UPDATE integrations.user_cohorts SET cohort_id = $1
                WHERE user_telegram_id = $2 AND cohort_id = $3
                """,
                cohort_id,
                telegram_id,
                existing,
            )
        else:
            await self._pool.execute(
                "INSERT INTO integrations.user_cohorts (user_telegram_id, cohort_id) VALUES ($1, $2)",
                telegram_id,
                cohort_id,
            )

    # --- Notion sync ---

    async def set_mentor_notion_page_id(self, telegram_id: int, page_id: str):
        await self._pool.execute(
            "UPDATE iam.mentors SET notion_page_id = $1 WHERE telegram_id = $2",
            page_id,
            telegram_id,
        )

    async def set_mentee_notion_page_id(self, telegram_id: int, page_id: str):
        await self._pool.execute(
            "UPDATE iam.mentees SET notion_page_id = $1 WHERE telegram_id = $2",
            page_id,
            telegram_id,
        )

    async def touch_updated_at(self, table: str, telegram_id: int):
        """Set updated_at = now() to force a push on next sync cycle."""
        await self._pool.execute(
            f"UPDATE {table} SET updated_at = NOW() WHERE telegram_id = $1",
            telegram_id,
        )

    # --- Meetings ---

    async def create_meeting(
        self,
        mentor_telegram_id: int,
        student_telegram_id: int,
        description: str = "E2E test meeting",
    ) -> int:
        """Create a meeting directly in DB. Returns meeting_id."""
        await self.ensure_user_record(mentor_telegram_id)
        await self.ensure_user_record(student_telegram_id)
        meeting_id = await self._pool.fetchval(
            """
            INSERT INTO meetings.meetings
                (mentor_telegram_id, student_telegram_id, description)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            mentor_telegram_id,
            student_telegram_id,
            description,
        )
        # Add participants via association table
        await self._pool.execute(
            "INSERT INTO meetings.meeting_users (meeting_id, telegram_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            meeting_id,
            mentor_telegram_id,
        )
        await self._pool.execute(
            "INSERT INTO meetings.meeting_users (meeting_id, telegram_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            meeting_id,
            student_telegram_id,
        )
        return meeting_id

    async def create_fake_users(
        self, count: int, role_name: str = "student"
    ) -> list[int]:
        """Create N fake non-placeholder users. Returns list of telegram_ids."""
        ids = []
        for i in range(count):
            tg_id = -(900_000 + i)
            await self._pool.execute(
                """
                INSERT INTO iam.users (telegram_id, name, role_id, is_placeholder)
                VALUES ($1, $2, (SELECT id FROM iam.roles WHERE name = $3), false)
                ON CONFLICT (telegram_id) DO NOTHING
                """,
                tg_id,
                f"FakeUser_{i}",
                role_name,
            )
            ids.append(tg_id)
        return ids

    async def create_role(self, name: str, display_name: str) -> int:
        """Create a role directly in DB. Returns role_id."""
        await self._pool.execute(
            "DELETE FROM iam.role_permissions WHERE role_id IN (SELECT id FROM iam.roles WHERE name = $1)",
            name,
        )
        await self._pool.execute("DELETE FROM iam.roles WHERE name = $1", name)
        return await self._pool.fetchval(
            "INSERT INTO iam.roles (name, display_name) VALUES ($1, $2) RETURNING id",
            name,
            display_name,
        )

    # --- Triggers ---

    async def create_trigger_rule(
        self,
        *,
        name: str,
        trigger_type: str,
        action_type: str,
        recipient_type: str,
        action_config: dict[str, Any],
        recipient_config: dict[str, Any] | None = None,
        trigger_config: dict[str, Any] | None = None,
        delay_seconds: int = 0,
    ) -> int:
        """Create a trigger rule directly in DB. Returns rule_id."""
        import json

        return await self._pool.fetchval(
            """
            INSERT INTO triggers.trigger_rules
                (name, trigger_type, action_type, recipient_type,
                 action_config, recipient_config, trigger_config,
                 delay_seconds, is_active)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8, true)
            RETURNING id
            """,
            name,
            trigger_type,
            action_type,
            recipient_type,
            json.dumps(action_config),
            json.dumps(recipient_config or {}),
            json.dumps(trigger_config or {}),
            delay_seconds,
        )
