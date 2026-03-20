import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.services.survey import (
    SurveyAccessDeniedError,
    SurveyNotAvailableError,
    SurveyService,
)
from src.survey.schemas import SurveyStatus, SurveySubmitRequest


def _participant(user_id: int, role_name: str) -> SimpleNamespace:
    role = SimpleNamespace(name=role_name)
    return SimpleNamespace(telegram_id=user_id, role=role)


def _meeting(
    *,
    completed: bool = True,
    has_response: bool = False,
) -> SimpleNamespace:
    completed_at = datetime.now(timezone.utc) if completed else None
    survey_available_at = datetime.now(timezone.utc) if completed else None
    response = SimpleNamespace(call_id=101, student_id=2) if has_response else None
    return SimpleNamespace(
        participants=[
            _participant(1, "mentor"),
            _participant(2, "student"),
        ],
        completed_at=completed_at,
        survey_available_at=survey_available_at,
        survey_response=response,
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _install_fake_survey_dao(
    monkeypatch: pytest.MonkeyPatch,
    *,
    get_call_with_participants,
    submit_response=None,
) -> None:
    module = types.ModuleType("src.dao.survey")

    class FakeSurveyDAO:
        @staticmethod
        async def get_call_with_participants(call_id: int):
            return await get_call_with_participants(call_id)

        @staticmethod
        async def submit_response(**kwargs):
            if submit_response is None:
                raise AssertionError("submit_response should not be called in this test")
            return await submit_response(**kwargs)

    module.SurveyDAO = FakeSurveyDAO
    monkeypatch.setitem(sys.modules, "src.dao.survey", module)


@pytest.mark.anyio
async def test_get_survey_state_for_student_available(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_call_with_participants(call_id: int):
        assert call_id == 101
        return _meeting(completed=True)

    _install_fake_survey_dao(
        monkeypatch,
        get_call_with_participants=fake_get_call_with_participants,
    )

    service = SurveyService()
    status, response = await service.get_survey_state_for_student(call_id=101, student_id=2)

    assert status == SurveyStatus.available
    assert response is None


@pytest.mark.anyio
async def test_get_survey_state_for_student_denies_mentor(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_call_with_participants(call_id: int):
        return _meeting(completed=True)

    _install_fake_survey_dao(
        monkeypatch,
        get_call_with_participants=fake_get_call_with_participants,
    )

    service = SurveyService()
    with pytest.raises(SurveyAccessDeniedError):
        await service.get_survey_state_for_student(call_id=101, student_id=1)


@pytest.mark.anyio
async def test_submit_survey_for_student_uses_student_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_get_call_with_participants(call_id: int):
        return _meeting(completed=True)

    async def fake_submit_response(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(call_id=kwargs["call_id"], student_id=kwargs["student_id"]), False

    _install_fake_survey_dao(
        monkeypatch,
        get_call_with_participants=fake_get_call_with_participants,
        submit_response=fake_submit_response,
    )

    payload = SurveySubmitRequest(
        duration_option="45_60",
        mentor_style=5,
        knowledge_depth=4,
        understanding=5,
        comment="Нормально",
    )

    service = SurveyService()
    response, already_submitted = await service.submit_survey_for_student(
        call_id=101,
        student_id=2,
        payload=payload,
    )

    assert already_submitted is False
    assert response.student_id == 2
    assert captured["call_id"] == 101
    assert captured["student_id"] == 2
    assert captured["duration_option"] == "45_60"
    assert captured["mentor_style"] == 5
    assert captured["knowledge_depth"] == 4
    assert captured["understanding"] == 5
    assert captured["comment"] == "Нормально"


@pytest.mark.anyio
async def test_submit_survey_for_student_requires_completed_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_call_with_participants(call_id: int):
        return _meeting(completed=False)

    _install_fake_survey_dao(
        monkeypatch,
        get_call_with_participants=fake_get_call_with_participants,
    )

    payload = SurveySubmitRequest(
        duration_option="45_60",
        mentor_style=5,
        knowledge_depth=4,
        understanding=5,
    )

    service = SurveyService()
    with pytest.raises(SurveyNotAvailableError):
        await service.submit_survey_for_student(
            call_id=101,
            student_id=2,
            payload=payload,
        )
