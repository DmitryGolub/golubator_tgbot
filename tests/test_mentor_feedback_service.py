from types import SimpleNamespace

import pytest

from src.mentor_feedback.constants import (
    MentorFeedbackDuration,
    MentorFeedbackStatus,
)
from src.mentor_feedback.dto import MentorFeedbackCreateData
from src.mentor_feedback.errors import (
    MentorFeedbackAlreadyExistsError,
    MentorNotInCallError,
)
from src.services import mentor_feedback as mentor_feedback_module
from src.services.mentor_feedback import MentorFeedbackService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _payload(**overrides) -> MentorFeedbackCreateData:
    data = {
        "status": MentorFeedbackStatus.ok,
        "duration": MentorFeedbackDuration.min_30_60,
        "motivation": 4,
        "neuromutation_stage": 7,
        "comment": "Голубь готов к следующему шагу",
    }
    data.update(overrides)
    return MentorFeedbackCreateData(**data)


@pytest.mark.anyio
async def test_create_feedback_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mentor_role = SimpleNamespace(name="mentor", display_name="Ментор", is_mentor=True, is_student=False)
    student_role = SimpleNamespace(name="student", display_name="Студент", is_mentor=False, is_student=True)
    meeting = SimpleNamespace(
        participants=[
            SimpleNamespace(telegram_id=9001, role_rel=mentor_role),
            SimpleNamespace(telegram_id=9002, role_rel=student_role),
        ]
    )
    created_feedback = SimpleNamespace(id=1, call_id=101)
    captured: dict[str, object] = {}

    async def fake_get_with_participants(call_id: int):
        assert call_id == 101
        return meeting

    async def fake_get_by_call_id(call_id: int):
        assert call_id == 101
        return None

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return created_feedback

    monkeypatch.setattr(
        mentor_feedback_module.MeetingDAO,
        "get_with_participants",
        fake_get_with_participants,
    )
    monkeypatch.setattr(
        mentor_feedback_module.MentorFeedbackDAO,
        "get_by_call_id",
        fake_get_by_call_id,
    )
    monkeypatch.setattr(
        mentor_feedback_module.MentorFeedbackDAO,
        "create",
        fake_create,
    )

    service = MentorFeedbackService()
    result = await service.create_feedback(
        call_id=101,
        mentor_id=9001,
        payload=_payload(),
    )

    assert result is created_feedback
    assert captured == {
        "call_id": 101,
        "mentor_id": 9001,
        "status": "ok",
        "duration": "min_30_60",
        "motivation": 4,
        "neuromutation_stage": 7,
        "comment": "Голубь готов к следующему шагу",
    }


@pytest.mark.anyio
async def test_create_feedback_duplicate_rejected_before_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mentor_role = SimpleNamespace(name="mentor", display_name="Ментор", is_mentor=True, is_student=False)
    meeting = SimpleNamespace(
        participants=[SimpleNamespace(telegram_id=9001, role_rel=mentor_role)]
    )

    async def fake_get_with_participants(call_id: int):
        return meeting

    async def fake_get_by_call_id(call_id: int):
        return object()

    monkeypatch.setattr(
        mentor_feedback_module.MeetingDAO,
        "get_with_participants",
        fake_get_with_participants,
    )
    monkeypatch.setattr(
        mentor_feedback_module.MentorFeedbackDAO,
        "get_by_call_id",
        fake_get_by_call_id,
    )

    service = MentorFeedbackService()

    with pytest.raises(MentorFeedbackAlreadyExistsError):
        await service.create_feedback(
            call_id=101,
            mentor_id=9001,
            payload=_payload(),
        )


@pytest.mark.anyio
async def test_create_feedback_rejects_mentor_outside_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    student_role = SimpleNamespace(name="student", display_name="Студент", is_mentor=False, is_student=True)
    meeting = SimpleNamespace(
        participants=[SimpleNamespace(telegram_id=9002, role_rel=student_role)]
    )

    async def fake_get_with_participants(call_id: int):
        return meeting

    monkeypatch.setattr(
        mentor_feedback_module.MeetingDAO,
        "get_with_participants",
        fake_get_with_participants,
    )

    service = MentorFeedbackService()

    with pytest.raises(MentorNotInCallError):
        await service.create_feedback(
            call_id=101,
            mentor_id=9001,
            payload=_payload(),
        )


def test_create_feedback_payload_validates_ranges() -> None:
    with pytest.raises(ValueError, match="Мотивация"):
        _payload(motivation=6)

    with pytest.raises(ValueError, match="Стадия"):
        _payload(neuromutation_stage=11)
