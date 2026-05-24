import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")


# ---------------------------------------------------------------------------
# Factory helpers — lightweight test doubles (SimpleNamespace)
# ---------------------------------------------------------------------------


def make_role(
    *,
    id: int = 1,
    name: str = "mentor",
    display_name: str = "Ментор",
    permissions: list | None = None,
):
    return SimpleNamespace(
        id=id,
        name=name,
        display_name=display_name,
        permissions=permissions or [],
        users=[],
    )


def make_user(
    *,
    telegram_id: int = 100,
    username: str = "testuser",
    name: str = "Test User",
    role_rel=None,
    registered_at: datetime | None = None,
):
    return SimpleNamespace(
        telegram_id=telegram_id,
        username=username,
        name=name,
        role_id=role_rel.id if role_rel else None,
        role_rel=role_rel,
        registered_at=registered_at or datetime.now(timezone.utc),
        updated_at=None,
        meetings=[],
        mentor_profile=None,
        mentee_profile=None,
    )


def make_meeting(
    *,
    id: int = 1,
    description: str = "Test meeting",
    scheduled_at: datetime | None = None,
    completed_at: datetime | None = None,
    call_started_at: datetime | None = None,
    participants: list | None = None,
    call_status=None,
    student_telegram_id: int | None = None,
    mentor_telegram_id: int | None = None,
    proposal_status=None,
    proposed_by: int | None = None,
    actual_duration_minutes: int | None = None,
    duration_answered_by: int | None = None,
):
    p_list = participants or []
    ns = SimpleNamespace(
        id=id,
        description=description,
        scheduled_at=scheduled_at,
        meeting_link=None,
        created_at=datetime.now(timezone.utc),
        completed_at=completed_at,
        call_started_at=call_started_at,
        notion_page_id=None,
        event_type=None,
        topic=None,
        mentor_telegram_id=mentor_telegram_id,
        mentee_telegram_tag=None,
        recording_link=None,
        summary=None,
        action_items=None,
        project=None,
        synced_at=None,
        updated_at=None,
        call_status=call_status,
        student_telegram_id=student_telegram_id,
        actual_duration_minutes=actual_duration_minutes,
        duration_answered_by=duration_answered_by,
        participants=p_list,
        student=None,
        proposal_status=proposal_status,
        proposed_by=proposed_by,
        is_cancelled=False,
        original_scheduled_at=None,
    )
    # Add computed properties matching Meeting model
    ns.other_participants = [p for p in p_list if p.telegram_id != mentor_telegram_id]
    ns.participant_ids = {p.telegram_id for p in p_list}

    # Computed duration properties matching Meeting model
    if ns.call_started_at and ns.completed_at:
        _duration = ns.completed_at - ns.call_started_at
        ns.call_duration = _duration
    else:
        ns.call_duration = None

    if ns.actual_duration_minutes is not None:
        ns.call_duration_minutes = ns.actual_duration_minutes
    elif ns.call_duration is not None:
        ns.call_duration_minutes = round(ns.call_duration.total_seconds() / 60)
    else:
        ns.call_duration_minutes = None

    return ns


def make_trigger_rule(
    *,
    id: int = 1,
    name: str = "Test rule",
    trigger_type: str = "manual",
    action_type: str = "send_survey",
    is_active: bool = True,
    cron_expression: str | None = None,
    regularity=None,
    time_of_day=None,
    delay_seconds: int = 0,
    delay_mode: str = "after_trigger",
    recipient_type: str = "event_student",
    recipient_config: dict | None = None,
    action_config: dict | None = None,
):
    return SimpleNamespace(
        id=id,
        name=name,
        trigger_type=trigger_type,
        action_type=action_type,
        is_active=is_active,
        cron_expression=cron_expression,
        regularity=regularity,
        time_of_day=time_of_day,
        delay_seconds=delay_seconds,
        delay_mode=delay_mode,
        recipient_type=recipient_type,
        recipient_config=recipient_config,
        action_config=action_config or {},
        created_by=None,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        executions=[],
    )


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.session = MagicMock()
    bot.session.close = AsyncMock()
    return bot
