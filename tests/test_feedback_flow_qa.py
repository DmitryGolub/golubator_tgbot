from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.bot.callbacks.mentor_feedback import (
    ChooseFeedbackDurationCB,
    ChooseFeedbackMeetingCB,
    ChooseFeedbackStatusCB,
)
from src.bot.callbacks.survey import SurveyDurationCB, SurveyRatingCB
from src.bot.handlers import mentor_feedback as mentor_feedback_handler
from src.bot.handlers import survey as survey_handler
from src.bot.handlers.common import menu as menu_handler
from src.bot.keyboards.mentor_feedback import (
    mentor_feedback_cancel_keyboard,
    mentor_feedback_duration_keyboard,
    mentor_feedback_status_keyboard,
)
from src.bot.keyboards.survey import (
    survey_comment_keyboard,
    survey_duration_keyboard,
    survey_rating_keyboard,
)
from src.bot.states.mentor_feedback import MentorFeedbackFSM
from src.bot.states.survey import SurveyFSM
from src.mentor_feedback.constants import (
    MentorFeedbackDuration,
    MentorFeedbackStatus,
)
from src.models.user import Role
from src.survey.constants import DurationOption
from src.survey.schemas import SurveyStatus


class FakeFSMContext:
    def __init__(self) -> None:
        self.current_state = None
        self.data: dict[str, object] = {}

    async def clear(self) -> None:
        self.current_state = None
        self.data.clear()

    async def set_state(self, state) -> None:
        self.current_state = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)


class FakeMessage:
    def __init__(self, user: SimpleNamespace, *, text: str | None = None) -> None:
        self.from_user = user
        self.text = text
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
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append(
            {
                "text": text,
                "show_alert": show_alert,
            }
        )


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


def _meeting(
    meeting_id: int,
    *,
    scheduled_at: datetime,
    student_name: str = "Student Example",
    completed_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=meeting_id,
        scheduled_at=scheduled_at,
        completed_at=completed_at,
        participants=[
            SimpleNamespace(name="Mentor Example", role=Role.mentor),
            SimpleNamespace(name=student_name, role=Role.student),
        ],
    )


def test_mentor_feedback_entrypoint_is_exposed_in_mentor_menu() -> None:
    mentor_meeting_callbacks = _callback_data(menu_handler._mentor_meetings_menu_kb())

    assert "mentor_feedback_start" in mentor_meeting_callbacks


def test_student_feedback_only_optional_comment_step_exposes_skip_control() -> None:
    duration_callbacks = _callback_data(survey_duration_keyboard(321))
    rating_callbacks = _callback_data(
        survey_rating_keyboard(321, survey_handler.QUESTION_MENTOR)
    )
    comment_callbacks = _callback_data(survey_comment_keyboard(321))

    assert not any(callback.startswith("survey_skip:") for callback in duration_callbacks)
    assert not any(callback.startswith("survey_skip:") for callback in rating_callbacks)
    assert any(callback.startswith("survey_skip:") for callback in comment_callbacks)


def test_mentor_feedback_only_optional_comment_step_exposes_skip_control() -> None:
    status_callbacks = _callback_data(mentor_feedback_status_keyboard())
    duration_callbacks = _callback_data(mentor_feedback_duration_keyboard())
    comment_callbacks = _callback_data(
        mentor_feedback_cancel_keyboard(allow_skip_comment=True)
    )

    assert "mentor_feedback_skip_comment" not in status_callbacks
    assert "mentor_feedback_skip_comment" not in duration_callbacks
    assert "mentor_feedback_skip_comment" in comment_callbacks


@pytest.mark.anyio
async def test_student_can_complete_feedback_flow_with_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_get_survey_state_for_student(self, *, call_id: int, student_id: int):
        captured["state_request"] = {
            "call_id": call_id,
            "student_id": student_id,
        }
        return SurveyStatus.available, None

    async def fake_submit_survey_for_student(
        self,
        *,
        call_id: int,
        student_id: int,
        payload,
    ):
        captured["submit"] = {
            "call_id": call_id,
            "student_id": student_id,
            "payload": payload,
        }
        return SimpleNamespace(call_id=call_id, student_id=student_id), False

    monkeypatch.setattr(
        survey_handler.SurveyService,
        "get_survey_state_for_student",
        fake_get_survey_state_for_student,
    )
    monkeypatch.setattr(
        survey_handler.SurveyService,
        "submit_survey_for_student",
        fake_submit_survey_for_student,
    )

    student = _user(
        9002,
        username="student_case",
        full_name="Student Example",
    )
    state = FakeFSMContext()
    start_message = FakeMessage(student)

    await survey_handler.cmd_survey(start_message, state, SimpleNamespace(args="321"))

    assert captured["state_request"] == {"call_id": 321, "student_id": 9002}
    assert state.current_state == SurveyFSM.choosing_duration
    assert await state.get_data() == {"call_id": 321}
    assert "1/5. Какая была длительность созвона?" in start_message.answers[-1]["text"]

    callback = FakeCallbackQuery(student)

    await survey_handler.cb_survey_duration(
        callback,
        SurveyDurationCB(call_id=321, option=DurationOption.between_45_60.value),
        state,
    )
    assert state.current_state == SurveyFSM.rating_mentor_style

    await survey_handler.cb_survey_mentor_style(
        callback,
        SurveyRatingCB(
            call_id=321,
            question=survey_handler.QUESTION_MENTOR,
            value=5,
        ),
        state,
    )
    assert state.current_state == SurveyFSM.rating_knowledge_depth

    await survey_handler.cb_survey_knowledge_depth(
        callback,
        SurveyRatingCB(
            call_id=321,
            question=survey_handler.QUESTION_KNOWLEDGE,
            value=4,
        ),
        state,
    )
    assert state.current_state == SurveyFSM.rating_understanding

    await survey_handler.cb_survey_understanding(
        callback,
        SurveyRatingCB(
            call_id=321,
            question=survey_handler.QUESTION_UNDERSTANDING,
            value=5,
        ),
        state,
    )
    assert state.current_state == SurveyFSM.waiting_comment

    comment_message = FakeMessage(
        student,
        text="Ментор хорошо объяснил сложную тему",
    )
    await survey_handler.msg_survey_comment(comment_message, state)

    submit_call = captured["submit"]
    payload = submit_call["payload"]

    assert submit_call["call_id"] == 321
    assert submit_call["student_id"] == 9002
    assert payload.duration_option == DurationOption.between_45_60
    assert payload.mentor_style == 5
    assert payload.knowledge_depth == 4
    assert payload.understanding == 5
    assert payload.comment == "Ментор хорошо объяснил сложную тему"
    assert state.current_state is None
    assert await state.get_data() == {}
    assert comment_message.answers[-1]["text"] == "Спасибо! Опрос по созвону #321 сохранён."


@pytest.mark.anyio
async def test_student_feedback_rejects_stale_buttons_from_other_call() -> None:
    student = _user(
        9002,
        username="student_case",
        full_name="Student Example",
    )
    state = FakeFSMContext()
    await state.set_state(SurveyFSM.choosing_duration)
    await state.update_data(call_id=321)
    callback = FakeCallbackQuery(student)

    await survey_handler.cb_survey_duration(
        callback,
        SurveyDurationCB(call_id=999, option=DurationOption.lt_30.value),
        state,
    )

    assert callback.answers[-1] == {
        "text": "Эта кнопка больше неактуальна.",
        "show_alert": True,
    }
    assert state.current_state == SurveyFSM.choosing_duration
    assert await state.get_data() == {"call_id": 321}
    assert callback.message.edits == []


@pytest.mark.anyio
async def test_mentor_can_complete_feedback_flow_with_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    now = datetime.now(timezone.utc)
    meetings = [
        _meeting(401, scheduled_at=now - timedelta(days=2), student_name="First Student"),
        _meeting(402, scheduled_at=now - timedelta(days=1), student_name="Second Student"),
    ]

    async def fake_get_feedback_candidates(mentor_id: int):
        captured["candidate_request"] = mentor_id
        return meetings

    async def fake_create_feedback(self, *, call_id: int, mentor_id: int, payload):
        captured["create_feedback"] = {
            "call_id": call_id,
            "mentor_id": mentor_id,
            "payload": payload,
        }
        return SimpleNamespace(id=1, call_id=call_id)

    monkeypatch.setattr(
        mentor_feedback_handler,
        "_get_feedback_candidates",
        fake_get_feedback_candidates,
    )
    monkeypatch.setattr(
        mentor_feedback_handler.MentorFeedbackService,
        "create_feedback",
        fake_create_feedback,
    )

    mentor = _user(
        7001,
        username="mentor_case",
        full_name="Mentor Example",
    )
    state = FakeFSMContext()
    callback = FakeCallbackQuery(mentor)

    await mentor_feedback_handler.cb_mentor_feedback_start(callback, state)

    assert captured["candidate_request"] == 7001
    assert state.current_state == MentorFeedbackFSM.choosing_meeting
    start_callbacks = _callback_data(callback.message.edits[-1]["reply_markup"])
    assert any(item.startswith("feedback_meeting:") for item in start_callbacks)

    await mentor_feedback_handler.cb_choose_feedback_meeting(
        callback,
        ChooseFeedbackMeetingCB(meeting_id=402),
        state,
    )
    assert state.current_state == MentorFeedbackFSM.choosing_status
    assert await state.get_data() == {"meeting_id": 402}

    await mentor_feedback_handler.cb_choose_feedback_status(
        callback,
        ChooseFeedbackStatusCB(value=MentorFeedbackStatus.ok.value),
        state,
    )
    assert state.current_state == MentorFeedbackFSM.choosing_duration

    await mentor_feedback_handler.cb_choose_feedback_duration(
        callback,
        ChooseFeedbackDurationCB(value=MentorFeedbackDuration.min_60_90.value),
        state,
    )
    assert state.current_state == MentorFeedbackFSM.waiting_motivation

    motivation_message = FakeMessage(mentor, text="5")
    await mentor_feedback_handler.msg_feedback_motivation(motivation_message, state)
    assert state.current_state == MentorFeedbackFSM.waiting_neuromutation_stage

    stage_message = FakeMessage(mentor, text="8")
    await mentor_feedback_handler.msg_feedback_neuromutation_stage(stage_message, state)
    assert state.current_state == MentorFeedbackFSM.waiting_comment

    comment_message = FakeMessage(
        mentor,
        text="Ученик уверенно справился с практической частью",
    )
    await mentor_feedback_handler.msg_feedback_comment(comment_message, state)

    create_feedback = captured["create_feedback"]
    payload = create_feedback["payload"]

    assert create_feedback["call_id"] == 402
    assert create_feedback["mentor_id"] == 7001
    assert payload.status == MentorFeedbackStatus.ok
    assert payload.duration == MentorFeedbackDuration.min_60_90
    assert payload.motivation == 5
    assert payload.neuromutation_stage == 8
    assert payload.comment == "Ученик уверенно справился с практической частью"
    assert state.current_state is None
    assert await state.get_data() == {}
    assert comment_message.answers[-1]["text"] == "Фидбек сохранен."


@pytest.mark.anyio
async def test_mentor_feedback_rejects_invalid_motivation_score() -> None:
    mentor = _user(
        7001,
        username="mentor_case",
        full_name="Mentor Example",
    )
    state = FakeFSMContext()
    await state.set_state(MentorFeedbackFSM.waiting_motivation)
    await state.update_data(meeting_id=402, status=MentorFeedbackStatus.ok.value)
    message = FakeMessage(mentor, text="9")

    await mentor_feedback_handler.msg_feedback_motivation(message, state)

    assert state.current_state == MentorFeedbackFSM.waiting_motivation
    assert await state.get_data() == {
        "meeting_id": 402,
        "status": MentorFeedbackStatus.ok.value,
    }
    assert message.answers[-1]["text"] == "Нужно число от 1 до 5."


@pytest.mark.anyio
@pytest.mark.xfail(
    reason="Менторский фидбек открывается по прошедшему scheduled_at, даже если completed_at не выставлен.",
)
async def test_mentor_feedback_candidates_require_completed_meeting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    incomplete_past_meeting = _meeting(
        777,
        scheduled_at=now - timedelta(hours=2),
        completed_at=None,
    )

    async def fake_get_for_user(user_id: int, *, hide_past: bool = False):
        assert user_id == 7001
        assert hide_past is False
        return [incomplete_past_meeting]

    async def fake_get_call_ids(call_ids: list[int]) -> set[int]:
        assert call_ids == [777]
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

    result = await mentor_feedback_handler._get_feedback_candidates(7001)

    assert result == []
