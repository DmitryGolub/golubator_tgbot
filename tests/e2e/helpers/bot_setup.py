"""BotSetup — performs test setup operations via bot UI instead of direct SQL writes."""

from __future__ import annotations

from typing import Any

import asyncpg

from tests.e2e.helpers.buttons import find_button
from tests.e2e.helpers.telegram_client import TelegramTestClient


class BotSetup:
    """Sets up test preconditions by navigating bot FSM dialogs.

    DB pool is used only for idempotent read-only pre-checks.
    All writes go through bot UI (admin account3).
    """

    def __init__(self, admin: TelegramTestClient, db_pool: asyncpg.Pool):
        self._admin = admin
        self._pool = db_pool

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _get_next_page_btn(self, msg, menu_name: str):
        """Find the → pagination button for the given menu name."""
        if not msg.reply_markup or not hasattr(msg.reply_markup, "rows"):
            return None
        for row in msg.reply_markup.rows:
            for btn in row.buttons:
                if btn.text == "→" and btn.data:
                    data = btn.data.decode()
                    if data.startswith(f"page:{menu_name}:"):
                        return btn
        return None

    def _has_button_data(self, msg, data: str) -> bool:
        if not msg.reply_markup or not hasattr(msg.reply_markup, "rows"):
            return False
        for row in msg.reply_markup.rows:
            for btn in row.buttons:
                if btn.data and btn.data.decode() == data:
                    return True
        return False

    async def _find_user_button(self, msg, telegram_id: int):
        """Navigate paginated user list (menu=users) and click the target user."""
        user_data = f"upd_user:{telegram_id}"
        while True:
            if self._has_button_data(msg, user_data):
                return await self._admin.click_button(msg, data=user_data)

            next_btn = self._get_next_page_btn(msg, "users")
            if next_btn is None:
                raise AssertionError(
                    f"User {telegram_id} not found in paginated users list"
                )
            msg = await self._admin.click_button(msg, data=next_btn.data.decode())

    # ── Role & permission setup ──────────────────────────────────────────────

    async def set_user_role(self, telegram_id: int, role_name: str) -> None:
        """Assign role to user via bot UI. Skips if already correct."""
        current = await self._pool.fetchval(
            """SELECT r.name FROM iam.users u
               LEFT JOIN iam.roles r ON u.role_id = r.id
               WHERE u.telegram_id = $1""",
            telegram_id,
        )
        if current == role_name:
            return

        msg = await self._admin.send_command("/menu")
        msg = await self._admin.click_button(msg, data="menu_users")
        msg = await self._admin.click_button(msg, data="user_update_menu")
        msg = await self._admin.click_button(msg, data="upd_param:role")
        msg = await self._admin.click_button(msg, data=f"upd_enum:role:{role_name}")
        await self._find_user_button(msg, telegram_id)

    async def ensure_role_permission(
        self, role_name: str, permission_name: str
    ) -> None:
        """Ensure role has permission, enabling it via bot UI if needed."""
        exists = await self._pool.fetchval(
            """SELECT 1 FROM iam.role_permissions rp
               JOIN iam.roles r ON rp.role_id = r.id
               JOIN iam.permissions p ON rp.permission_id = p.id
               WHERE r.name = $1 AND p.codename = $2""",
            role_name,
            permission_name,
        )
        if exists:
            return

        role_id = await self._pool.fetchval(
            "SELECT id FROM iam.roles WHERE name = $1", role_name
        )
        perm_id = await self._pool.fetchval(
            "SELECT id FROM iam.permissions WHERE codename = $1", permission_name
        )
        assert role_id is not None, f"Role {role_name!r} not found"
        assert perm_id is not None, f"Permission {permission_name!r} not found"

        msg = await self._admin.send_command("/menu")
        msg = await self._admin.click_button(msg, data="menu_roles")
        msg = await self._admin.click_button(msg, data=f"rbac_role:{role_id}")
        msg = await self._admin.click_button(msg, data=f"rbac_edit_perms:{role_id}")

        perm_data = f"rbac_perm:{role_id}:{perm_id}"
        if not self._has_button_data(msg, perm_data):
            raise AssertionError(
                f"Permission button {perm_data} not found in permissions keyboard"
            )

        # Find button — click only if it shows ❌ (not yet enabled)
        for row in msg.reply_markup.rows:
            for btn in row.buttons:
                if btn.data and btn.data.decode() == perm_data:
                    if btn.text.startswith("❌"):
                        await self._admin.click_button(msg, data=perm_data)
                    return

    async def create_role(self, name: str, display_name: str) -> int:
        """Create role via bot UI. Returns existing ID if role already exists."""
        existing = await self._pool.fetchval(
            "SELECT id FROM iam.roles WHERE name = $1", name
        )
        if existing is not None:
            return existing

        msg = await self._admin.send_command("/menu")
        msg = await self._admin.click_button(msg, data="menu_roles")
        await self._admin.click_button(msg, data="rbac_create_role")
        await self._admin.send_text_in_fsm(name)
        await self._admin.send_text_in_fsm(display_name)

        role_id = await self._pool.fetchval(
            "SELECT id FROM iam.roles WHERE name = $1", name
        )
        assert role_id is not None, f"Role {name!r} was not created"
        return role_id

    async def create_test_role_with_perms(
        self, name: str, display_name: str, permissions: list[str]
    ) -> int:
        """Create role with permissions. Orchestrates create_role + ensure_role_permission."""
        role_id = await self.create_role(name, display_name)
        for perm in permissions:
            await self.ensure_role_permission(name, perm)
        return role_id

    # ── Cohort setup ─────────────────────────────────────────────────────────

    async def set_user_cohort(
        self, telegram_id: int, cohort_type: str, cohort_value: str
    ) -> None:
        """Set user cohort via bot UI. Skips if already correct."""
        existing = await self._pool.fetchval(
            """SELECT c.value FROM integrations.user_cohorts uc
               JOIN integrations.cohorts c ON uc.cohort_id = c.id
               WHERE uc.user_telegram_id = $1 AND c.type = $2""",
            telegram_id,
            cohort_type,
        )
        if existing == cohort_value:
            return

        # Ensure the cohort value exists so the keyboard button will be present
        await self._pool.execute(
            "INSERT INTO integrations.cohorts (type, value) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            cohort_type,
            cohort_value,
        )

        msg = await self._admin.send_command("/menu")
        msg = await self._admin.click_button(msg, data="menu_users")
        msg = await self._admin.click_button(msg, data="user_update_menu")

        if cohort_type == "Status":
            msg = await self._admin.click_button(msg, data="upd_param:status")
            msg = await self._admin.click_button(
                msg, data=f"upd_enum:status:{cohort_value}"
            )
        else:
            msg = await self._admin.click_button(msg, data="upd_param:cohort")
            msg = await self._admin.click_button(msg, data=f"upd_ctype:{cohort_type}")
            msg = await self._admin.click_button(
                msg, data=f"upd_enum:cohort:{cohort_value}"
            )

        await self._find_user_button(msg, telegram_id)

    # ── Survey template setup ────────────────────────────────────────────────

    async def create_survey_template(
        self, title: str, slug: str, questions: list[dict[str, Any]]
    ) -> int:
        """Create survey template via bot FSM. Returns existing ID if slug already exists."""
        existing = await self._pool.fetchval(
            "SELECT id FROM surveys.survey_templates WHERE slug = $1", slug
        )
        if existing is not None:
            return existing

        msg = await self._admin.send_command("/menu")
        msg = await self._admin.click_button(msg, data="menu_surveys")
        await self._admin.click_button(msg, data="sb_action:create")

        # Header: title -> slug -> description (skip with "-")
        await self._admin.send_text_in_fsm(title)
        await self._admin.send_text_in_fsm(slug)
        await self._admin.send_text_in_fsm("-")

        for i, q in enumerate(questions):
            is_last = i == len(questions) - 1
            qtype = q["type"]

            # Enter question title — bot responds with question type keyboard
            type_msg = await self._admin.send_text_in_fsm(q["title"])

            if qtype == "text":
                # click type → _save_question → bot sends NEW "Question added" message
                after_q_msg = await self._admin.click_button(
                    type_msg, data="sq_type:text"
                )

            elif qtype == "rating":
                # click type → bot EDITS to "Enter min"
                await self._admin.click_button(type_msg, data="sq_type:rating")
                config = q.get("config", {})
                min_val = config.get("min", 1)
                max_val = config.get("max", 5)
                await self._admin.send_text_in_fsm(str(min_val))
                # last send returns "Question added" message
                after_q_msg = await self._admin.send_text_in_fsm(str(max_val))

            elif qtype in ("single_choice", "multiple_choice"):
                # click type → bot EDITS to "Enter option value"
                await self._admin.click_button(type_msg, data=f"sq_type:{qtype}")
                options = q.get("options", [])
                opt_msg = None
                for opt in options:
                    await self._admin.send_text_in_fsm(opt["value"])
                    opt_msg = await self._admin.send_text_in_fsm(opt["label"])
                assert opt_msg is not None, f"Question {q['title']!r} has no options"
                # opt_msg has options_done button; click → "Question added"
                after_q_msg = await self._admin.click_button(
                    opt_msg, data="sb_action:options_done"
                )

            else:
                raise ValueError(f"Unknown question type: {qtype!r}")

            if not is_last:
                await self._admin.click_button(
                    after_q_msg, data="sb_action:add_question"
                )
            else:
                await self._admin.click_button(after_q_msg, data="sb_action:finish")

        template_id = await self._pool.fetchval(
            "SELECT id FROM surveys.survey_templates WHERE slug = $1", slug
        )
        assert template_id is not None, f"Survey template {slug!r} was not created"
        return template_id

    # ── Meeting setup ────────────────────────────────────────────────────────

    async def create_meeting(
        self,
        mentor_client: TelegramTestClient,
        mentor_telegram_id: int,
        student_client: TelegramTestClient,
        student_telegram_id: int,
        description: str,
        time_str: str = "18:00",
    ) -> int:
        """Create a meeting via FSM and have student confirm the proposal. Returns meeting_id."""
        menu_msg = await mentor_client.send_command("/menu")
        meetings_btn = find_button(menu_msg, "mentor_meetings_menu")
        assert meetings_btn is not None, "Mentor menu should have meetings button"
        meetings_msg = await mentor_client.click_button(
            menu_msg, text=meetings_btn.text
        )

        create_btn = find_button(meetings_msg, "meeting_create")
        assert create_btn is not None, "Meetings list should have 'Create' button"
        create_msg = await mentor_client.click_button(
            meetings_msg, text=create_btn.text
        )

        # Step 1: Choose student — prefer exact match, fall back to first available
        student_data = f"meeting_student:{student_telegram_id}"
        if self._has_button_data(create_msg, student_data):
            type_msg = await mentor_client.click_button(create_msg, data=student_data)
        else:
            student_btn = find_button(create_msg, "meeting_student:")
            assert student_btn is not None, (
                f"Should find student button for {student_telegram_id}"
            )
            type_msg = await mentor_client.click_button(
                create_msg, data=student_btn.data.decode()
            )

        # Step 2: Skip meeting type (or pick first available)
        skip_type_btn = find_button(type_msg, "meeting_skip_type")
        if skip_type_btn:
            await mentor_client.click_button(type_msg, text=skip_type_btn.text)
        else:
            type_btn = find_button(type_msg, "meeting_type:")
            assert type_btn is not None, "Should have type buttons"
            await mentor_client.click_button(type_msg, text=type_btn.text)

        # Step 3: Enter description
        date_msg = await mentor_client.send_text_in_fsm(description)

        # Step 4: Choose first available date from calendar
        date_btn = find_button(date_msg, "meeting_date:")
        assert date_btn is not None, "Should find date button in calendar"
        await mentor_client.click_button(date_msg, text=date_btn.text)

        # Step 5: Enter time
        link_msg = await mentor_client.send_text_in_fsm(time_str)

        # Snapshot BEFORE step 6 — proposal is sent synchronously during finalization
        snapshot_id = await student_client.snapshot_last_message_id()

        # Step 6: Skip link
        skip_link_btn = find_button(link_msg, "meeting_skip_link")
        if skip_link_btn:
            await mentor_client.click_button(link_msg, text=skip_link_btn.text)
        else:
            await mentor_client.send_text_in_fsm("https://meet.example.com/e2e")
        proposal_msg = await student_client.wait_for_message_after(snapshot_id)
        confirm_btn = find_button(proposal_msg, "mtg_confirm:")
        assert confirm_btn is not None, (
            "Student should receive a proposal with confirm button"
        )
        await student_client.click_button(proposal_msg, text=confirm_btn.text)

        meeting_id = await self._pool.fetchval(
            """SELECT id FROM meetings.meetings
               WHERE mentor_telegram_id = $1 AND student_telegram_id = $2
               ORDER BY created_at DESC LIMIT 1""",
            mentor_telegram_id,
            student_telegram_id,
        )
        assert meeting_id is not None, "Meeting should be created in DB"
        return meeting_id

    # ── Trigger rule setup ───────────────────────────────────────────────────

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
        """Create trigger rule via bot FSM. Returns existing ID if name already exists."""
        existing = await self._pool.fetchval(
            "SELECT id FROM triggers.trigger_rules WHERE name = $1", name
        )
        if existing is not None:
            return existing

        msg = await self._admin.send_command("/menu")
        msg = await self._admin.click_button(msg, data="menu_triggers")
        await self._admin.click_button(msg, data="tr_action:create")

        # Step 1: enter name → bot sends "Choose trigger type"
        type_msg = await self._admin.send_text_in_fsm(name)

        # Step 2: click trigger type
        msg = await self._admin.click_button(type_msg, data=f"tr_type:{trigger_type}")

        # Step 3: trigger-specific config
        if trigger_type == "periodic_cron":
            cfg = trigger_config or {}
            if "cron" in cfg:
                msg = await self._admin.click_button(msg, data="tr_smode:cron")
                msg = await self._admin.send_text_in_fsm(cfg["cron"])
            else:
                regularity = cfg.get("regularity", "day")
                time_of_day = cfg.get("time_of_day", "09:00")
                msg = await self._admin.click_button(msg, data="tr_smode:regularity")
                msg = await self._admin.click_button(msg, data=f"tr_reg:{regularity}")
                msg = await self._admin.send_text_in_fsm(time_of_day)

        elif trigger_type == "cohort_changed":
            cfg = trigger_config or {}
            cohort_type = cfg.get("cohort_type", "*")
            from_value = cfg.get("from_value", "*")
            to_value = cfg.get("to_value", "*")
            msg = await self._admin.click_button(msg, data=f"tr_ctype:{cohort_type}")
            msg = await self._admin.click_button(msg, data=f"tr_cval:{from_value}")
            msg = await self._admin.click_button(msg, data=f"tr_cval:{to_value}")
        # other types (manual, call_ended, meeting_created): go directly to action type

        # Step 4: click action type
        msg = await self._admin.click_button(msg, data=f"tr_atype:{action_type}")

        # Step 5: action-specific config
        if action_type == "send_notification":
            text = action_config.get("text", "")
            msg = await self._admin.send_text_in_fsm(text)
        elif action_type == "send_survey":
            template_id = action_config["survey_template_id"]
            msg = await self._admin.click_button(msg, data=f"tr_survey:{template_id}")

        # Step 6: click recipient type
        await self._admin.click_button(msg, data=f"tr_rtype:{recipient_type}")

        # Step 7: recipient-specific config (if needed)
        if recipient_type in ("by_role", "by_state", "by_cohort", "specific_users"):
            rc = recipient_config or {}
            if recipient_type == "by_role":
                config_text = rc.get("role_name", "")
            elif recipient_type == "by_state":
                config_text = rc.get("state", "")
            elif recipient_type == "by_cohort":
                config_text = rc.get("cohort_value", "")
            else:  # specific_users
                config_text = ",".join(str(uid) for uid in rc.get("user_ids", []))
            await self._admin.send_text_in_fsm(config_text)

        # Step 8: enter delay
        await self._admin.send_text_in_fsm(str(delay_seconds))

        rule_id = await self._pool.fetchval(
            "SELECT id FROM triggers.trigger_rules WHERE name = $1", name
        )
        assert rule_id is not None, f"Trigger rule {name!r} was not created"
        return rule_id
