import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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

import src.services.call_flow as call_flow_module
from src.bot.handlers import mentor_feedback as mentor_feedback_handler
from src.bot.handlers.common import menu as menu_handler
from src.bot.keyboards.meeting import mentor_meetings_keyboard
from src.models.call import CallStatus
from src.models.user import Role
from src.services.call_flow import (
    ActiveCallAlreadyExistsError,
    ActiveCallNotFoundError,
    CallFlowService,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _participant(user_id: int, role: Role) -> SimpleNamespace:
    return SimpleNamespace(
        telegram_id=user_id,
        role=role,
        name=f"user-{user_id}",
        username=f"user_{user_id}",
    )


@pytest.mark.anyio
async def test_start_call_creates_active_call_for_meeting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting = SimpleNamespace(
        id=101,
        completed_at=None,
        participants=[
            _participant(1001, Role.mentor),
            _participant(2002, Role.student),
        ],
    )
    created_call = SimpleNamespace(id=77, meeting_id=101)
    captured: dict[str, int] = {}

    async def fake_get_with_participants(meeting_id: int):
        assert meeting_id == 101
        return meeting

    async def fake_get_active_for_mentor(mentor_id: int):
        assert mentor_id == 1001
        return None

    async def fake_get_by_meeting_id(meeting_id: int):
        assert meeting_id == 101
        return None

    async def fake_create_for_meeting(**kwargs):
        captured.update(kwargs)
        return created_call

    monkeypatch.setattr(
        call_flow_module.MeetingDAO,
        "get_with_participants",
        fake_get_with_participants,
    )
    monkeypatch.setattr(
        call_flow_module.CallDAO,
        "get_active_for_mentor",
        fake_get_active_for_mentor,
    )
    monkeypatch.setattr(
        call_flow_module.CallDAO,
        "get_by_meeting_id",
        fake_get_by_meeting_id,
    )
    monkeypatch.setattr(
        call_flow_module.CallDAO,
        "create_for_meeting",
        fake_create_for_meeting,
    )

    service = CallFlowService()
    result = await service.start_call(mentor_id=1001, meeting_id=101)

    assert result is created_call
    assert captured == {
        "meeting_id": 101,
        "mentor_id": 1001,
        "student_id": 2002,
    }


@pytest.mark.anyio
async def test_start_call_rejects_existing_active_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting = SimpleNamespace(
        id=101,
        completed_at=None,
        participants=[
            _participant(1001, Role.mentor),
            _participant(2002, Role.student),
        ],
    )
    active_call = SimpleNamespace(id=77, meeting_id=999)

    async def fake_get_with_participants(meeting_id: int):
        return meeting

    async def fake_get_active_for_mentor(mentor_id: int):
        return active_call

    monkeypatch.setattr(
        call_flow_module.MeetingDAO,
        "get_with_participants",
        fake_get_with_participants,
    )
    monkeypatch.setattr(
        call_flow_module.CallDAO,
        "get_active_for_mentor",
        fake_get_active_for_mentor,
    )

    service = CallFlowService()
    with pytest.raises(ActiveCallAlreadyExistsError) as exc_info:
        await service.start_call(mentor_id=1001, meeting_id=101)

    assert exc_info.value.call is active_call


@pytest.mark.anyio
async def test_end_active_call_marks_meeting_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_call = SimpleNamespace(id=77, meeting_id=101)
    finished_call = SimpleNamespace(
        id=77,
        meeting_id=101,
        started_at=datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 19, 11, 0, tzinfo=timezone.utc),
        status=CallStatus.finished,
    )
    completed_meeting = SimpleNamespace(id=101)

    async def fake_get_active_for_mentor(mentor_id: int):
        assert mentor_id == 1001
        return active_call

    async def fake_finish_call(call_id: int, mentor_id: int):
        assert call_id == 77
        assert mentor_id == 1001
        return finished_call

    async def fake_complete(meeting_id: int, *, completed_at):
        assert meeting_id == 101
        assert completed_at == finished_call.ended_at
        return completed_meeting, True

    monkeypatch.setattr(
        call_flow_module.CallDAO,
        "get_active_for_mentor",
        fake_get_active_for_mentor,
    )
    monkeypatch.setattr(
        call_flow_module.CallDAO,
        "finish_call",
        fake_finish_call,
    )
    monkeypatch.setattr(
        call_flow_module.MeetingDAO,
        "complete",
        fake_complete,
    )

    service = CallFlowService()
    result = await service.end_active_call(mentor_id=1001)

    assert result.call is finished_call
    assert result.meeting is completed_meeting
    assert result.meeting_was_completed is True


@pytest.mark.anyio
async def test_end_active_call_requires_existing_active_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_active_for_mentor(mentor_id: int):
        return None

    monkeypatch.setattr(
        call_flow_module.CallDAO,
        "get_active_for_mentor",
        fake_get_active_for_mentor,
    )

    service = CallFlowService()
    with pytest.raises(ActiveCallNotFoundError):
        await service.end_active_call(mentor_id=1001)


def test_end_call_command_handler_registered() -> None:
    handler_names = [handler.callback.__name__ for handler in menu_handler.router.message.handlers]
    assert "cmd_end_call" in handler_names


def test_mentor_meetings_keyboard_contains_end_call_button() -> None:
    meeting = SimpleNamespace(id=101, completed_at=None)
    keyboard = mentor_meetings_keyboard([meeting])

    texts = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "Завершить активный созвон" in texts
    assert "Начать созвон #101" in texts


@pytest.mark.anyio
async def test_feedback_candidates_use_completed_at_instead_of_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_meeting = SimpleNamespace(
        id=101,
        completed_at=datetime(2026, 3, 19, 11, 0, tzinfo=timezone.utc),
        scheduled_at=datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
    )
    not_completed_meeting = SimpleNamespace(
        id=202,
        completed_at=None,
        scheduled_at=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
    )

    async def fake_get_for_user(mentor_id: int):
        assert mentor_id == 9001
        return [completed_meeting, not_completed_meeting]

    async def fake_get_call_ids(call_ids: list[int]):
        assert call_ids == [101]
        return set()

    monkeypatch.setattr(
        mentor_feedback_handler.MeetingDAO,
        "get_for_user",
        fake_get_for_user,
    )
    monkeypatch.setattr(
        mentor_feedback_handler.MentorFeedbackDAO,
        "get_call_ids",
        fake_get_call_ids,
    )

    meetings = await mentor_feedback_handler._get_feedback_candidates(9001)

    assert meetings == [completed_meeting]


@pytest.mark.anyio
async def test_feedback_candidates_skip_meetings_with_saved_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting = SimpleNamespace(
        id=101,
        completed_at=datetime(2026, 3, 19, 11, 0, tzinfo=timezone.utc),
        scheduled_at=datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc),
    )

    async def fake_get_for_user(mentor_id: int):
        return [meeting]

    async def fake_get_call_ids(call_ids: list[int]):
        return {101}

    monkeypatch.setattr(
        mentor_feedback_handler.MeetingDAO,
        "get_for_user",
        fake_get_for_user,
    )
    monkeypatch.setattr(
        mentor_feedback_handler.MentorFeedbackDAO,
        "get_call_ids",
        fake_get_call_ids,
    )

    meetings = await mentor_feedback_handler._get_feedback_candidates(9001)

    assert meetings == []
