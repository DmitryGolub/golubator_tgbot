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
    is_mentor: bool = False,
    is_student: bool = False,
    permissions: list | None = None,
):
    return SimpleNamespace(
        id=id,
        name=name,
        display_name=display_name,
        is_mentor=is_mentor,
        is_student=is_student,
        permissions=permissions or [],
        users=[],
    )


def make_user(
    *,
    telegram_id: int = 100,
    username: str = "testuser",
    name: str = "Test User",
    role_rel=None,
    state=None,
    mentor_id: int | None = None,
    registered_at: datetime | None = None,
):
    return SimpleNamespace(
        telegram_id=telegram_id,
        username=username,
        name=name,
        role="student",
        role_id=role_rel.id if role_rel else None,
        role_rel=role_rel,
        state=state or "greeting",
        mentor_id=mentor_id,
        notion_page_id=None,
        notion_source_db=None,
        registered_at=registered_at or datetime.now(timezone.utc),
        state_changed_at=None,
        synced_at=None,
        updated_at=None,
        meetings=[],
        cohort_cache=[],
        mentor=None,
        students=[],
        mentor_calls=[],
        student_calls=[],
        tags=[],
    )


def make_meeting(
    *,
    id: int = 1,
    description: str = "Test meeting",
    scheduled_at: datetime | None = None,
    completed_at: datetime | None = None,
    participants: list | None = None,
    call=None,
):
    return SimpleNamespace(
        id=id,
        description=description,
        scheduled_at=scheduled_at,
        meeting_link=None,
        created_at=datetime.now(timezone.utc),
        completed_at=completed_at,
        notion_page_id=None,
        event_type=None,
        topic=None,
        mentor_telegram_id=None,
        mentee_telegram_tag=None,
        recording_link=None,
        summary=None,
        action_items=None,
        project=None,
        synced_at=None,
        updated_at=None,
        participants=participants or [],
        call=call,
    )


def make_call(
    *,
    id: int = 1,
    meeting_id: int = 1,
    mentor_id: int = 100,
    student_id: int = 200,
    status: str = "ongoing",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    meeting=None,
):
    return SimpleNamespace(
        id=id,
        meeting_id=meeting_id,
        mentor_id=mentor_id,
        student_id=student_id,
        status=status,
        started_at=started_at or datetime.now(timezone.utc),
        ended_at=ended_at,
        updated_at=None,
        meeting=meeting,
        mentor=None,
        student=None,
    )


def make_trigger_rule(
    *,
    id: int = 1,
    name: str = "Test rule",
    trigger_type: str = "manual",
    action_type: str = "send_notification",
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
