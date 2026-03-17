from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.bot.handlers.common import menu as menu_handler
from src.bot.handlers.common import start as start_handler
from src.bot.keyboards.menu import menu_keyboard
from src.models.user import Role, State


class FakeMessage:
    def __init__(self, user: SimpleNamespace) -> None:
        self.from_user = user
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append(
            {
                "text": text,
                "reply_markup": reply_markup,
            }
        )


class FakeEditableMessage:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edits.append(
            {
                "text": text,
                "reply_markup": reply_markup,
            }
        )


class FakeCallbackQuery:
    def __init__(self, user: SimpleNamespace) -> None:
        self.from_user = user
        self.message = FakeEditableMessage()
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


def _user(
    user_id: int,
    *,
    username: str,
    full_name: str,
) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, username=username, full_name=full_name)


def _callback_data(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def _source_tree_text(*relative_parts: str) -> str:
    root = Path(__file__).resolve().parents[1]
    path = root.joinpath(*relative_parts)
    return path.read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_student_registration_creates_student_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_find_one_or_none(**filter_by):
        captured["find_one_or_none"] = filter_by
        return None

    async def fake_add(**data):
        captured["add"] = data
        return SimpleNamespace(
            telegram_id=data["telegram_id"],
            registered_at=data["registered_at"],
        )

    async def fake_schedule_onboarding_notifications(user, *, base_time=None):
        captured["scheduled_notifications"] = {
            "user": user,
            "base_time": base_time,
        }

    monkeypatch.setattr(start_handler.UserDAO, "find_one_or_none", fake_find_one_or_none)
    monkeypatch.setattr(start_handler.UserDAO, "add", fake_add)
    monkeypatch.setattr(
        start_handler,
        "schedule_onboarding_notifications",
        fake_schedule_onboarding_notifications,
    )

    message = FakeMessage(
        _user(
            1001,
            username="student_case",
            full_name="Student Example",
        )
    )

    await start_handler.cmd_start(message)

    added_user = captured["add"]
    assert captured["find_one_or_none"] == {"telegram_id": 1001}
    assert added_user["telegram_id"] == 1001
    assert added_user["username"] == "student_case"
    assert added_user["name"] == "Student Example"
    assert added_user["role"] == Role.student
    assert added_user["state"] == State.greeting
    assert added_user["registered_at"].tzinfo is not None
    assert captured["scheduled_notifications"]["base_time"] == added_user["registered_at"]
    assert message.answers[-1]["text"] == start_handler.WELCOME_TEXT


@pytest.mark.anyio
async def test_mentor_can_finish_active_call_via_existing_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finished_call = SimpleNamespace(
        id=77,
        started_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 18, 10, 45, tzinfo=timezone.utc),
    )
    captured: dict[str, object] = {}

    async def fake_get_active_for_mentor(mentor_id: int):
        captured["get_active_for_mentor"] = mentor_id
        return SimpleNamespace(id=77)

    async def fake_finish_call(call_id: int, mentor_id: int):
        captured["finish_call"] = {
            "call_id": call_id,
            "mentor_id": mentor_id,
        }
        return finished_call

    monkeypatch.setattr(menu_handler.CallDAO, "get_active_for_mentor", fake_get_active_for_mentor)
    monkeypatch.setattr(menu_handler.CallDAO, "finish_call", fake_finish_call)

    callback = FakeCallbackQuery(
        _user(
            501,
            username="mentor_case",
            full_name="Mentor Example",
        )
    )

    await menu_handler.cb_mentor_end_call(callback)

    assert callback.answered is True
    assert captured["get_active_for_mentor"] == 501
    assert captured["finish_call"] == {"call_id": 77, "mentor_id": 501}
    assert "Созвон #77 завершён." in callback.message.edits[-1]["text"]
    assert "call_id=77" in callback.message.edits[-1]["text"]


@pytest.mark.anyio
async def test_mentor_end_call_without_active_call_shows_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_active_for_mentor(mentor_id: int):
        assert mentor_id == 501
        return None

    monkeypatch.setattr(menu_handler.CallDAO, "get_active_for_mentor", fake_get_active_for_mentor)

    callback = FakeCallbackQuery(
        _user(
            501,
            username="mentor_case",
            full_name="Mentor Example",
        )
    )

    await menu_handler.cb_mentor_end_call(callback)

    assert callback.answered is True
    assert callback.message.edits[-1]["text"] == "У вас нет активного созвона."


def test_student_menu_has_no_call_completion_controls() -> None:
    student_menu_callbacks = _callback_data(menu_keyboard(Role.student))

    assert "mentor_end_call" not in student_menu_callbacks


def test_existing_end_call_callback_is_not_exposed_in_mentor_menu() -> None:
    mentor_meeting_callbacks = _callback_data(menu_handler._mentor_meetings_menu_kb())

    assert "mentor_end_call" not in mentor_meeting_callbacks


@pytest.mark.xfail(
    reason="Требуемая команда /end_call не зарегистрирована в коде бота.",
)
def test_required_end_call_command_is_registered() -> None:
    bot_handlers_source = _source_tree_text("src", "bot", "handlers", "common", "menu.py")

    assert 'Command("end_call")' in bot_handlers_source or "Command('end_call')" in bot_handlers_source


@pytest.mark.xfail(
    reason="У ментора нет пользовательского действия для старта активного созвона.",
)
def test_required_call_start_action_is_exposed_to_mentor() -> None:
    mentor_meeting_callbacks = _callback_data(menu_handler._mentor_meetings_menu_kb())

    assert any("call" in callback and "end" not in callback for callback in mentor_meeting_callbacks)
