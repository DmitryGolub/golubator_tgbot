import asyncpg
from typing import Any


class TestSetup:
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

    async def ensure_mentor_record(self, telegram_id: int):
        """Create a Mentor record if it doesn't exist."""
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
                    (template_id, title, question_type, position, is_required, config)
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
                        (question_id, value, label, position)
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
                (template_id, respondent_telegram_id, context_type, context_id, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING id
            """,
            template_id,
            respondent_id,
            context_type,
            context_id,
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
            SELECT id FROM integrations.user_cohorts
            WHERE user_telegram_id = $1 AND cohort_id IN (
                SELECT id FROM integrations.cohorts WHERE type = $2
            )
            """,
            telegram_id,
            cohort_type,
        )
        if existing:
            await self._pool.execute(
                "UPDATE integrations.user_cohorts SET cohort_id = $1 WHERE id = $2",
                cohort_id,
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
