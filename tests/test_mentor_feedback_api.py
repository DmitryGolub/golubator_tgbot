from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import pytest

from src.api.dependencies import get_mentor_feedback_service
from src.api.main import app
from src.mentor_feedback.errors import (
    CallNotFoundError,
    MentorFeedbackAlreadyExistsError,
    MentorNotInCallError,
)


@dataclass
class FakeMentorFeedback:
    id: int
    call_id: int
    mentor_id: int
    status: str
    duration: str
    motivation: int
    neuromutation_stage: int
    comment: str | None
    created_at: datetime


class FakeMentorFeedbackService:
    def __init__(self) -> None:
        self.calls = {
            101: {"mentor_id": 9001},
            202: {"mentor_id": 9002},
        }
        self.responses: dict[int, FakeMentorFeedback] = {}
        self._next_id = 1

    async def create_feedback(self, *, call_id: int, mentor_id: int, payload):
        if call_id not in self.calls:
            raise CallNotFoundError

        expected_mentor_id = self.calls[call_id]["mentor_id"]
        if mentor_id != expected_mentor_id:
            raise MentorNotInCallError

        if call_id in self.responses:
            raise MentorFeedbackAlreadyExistsError

        feedback = FakeMentorFeedback(
            id=self._next_id,
            call_id=call_id,
            mentor_id=mentor_id,
            status=payload.status.value,
            duration=payload.duration.value,
            motivation=payload.motivation,
            neuromutation_stage=payload.neuromutation_stage,
            comment=payload.comment,
            created_at=datetime.now(timezone.utc),
        )
        self.responses[call_id] = feedback
        self._next_id += 1
        return feedback


@pytest.fixture
def fake_service() -> FakeMentorFeedbackService:
    service = FakeMentorFeedbackService()

    async def override_service() -> FakeMentorFeedbackService:
        return service

    app.dependency_overrides[get_mentor_feedback_service] = override_service
    try:
        yield service
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _payload(**overrides) -> dict:
    payload = {
        "mentor_id": 9001,
        "status": "ok",
        "duration": "min_30_60",
        "motivation": 4,
        "neuromutation_stage": 7,
        "comment": "Голубь готов к следующему шагу",
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_create_mentor_feedback_success(fake_service: FakeMentorFeedbackService) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.post(
            "/calls/101/mentor-feedback",
            json=_payload(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["call_id"] == 101
    assert body["mentor_id"] == 9001
    assert body["status"] == "ok"
    assert body["duration"] == "min_30_60"
    assert body["motivation"] == 4
    assert body["neuromutation_stage"] == 7
    assert body["comment"] == "Голубь готов к следующему шагу"
    assert "created_at" in body
    assert fake_service.responses[101].call_id == 101


@pytest.mark.anyio
async def test_create_mentor_feedback_duplicate_returns_conflict(
    fake_service: FakeMentorFeedbackService,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        first = await test_client.post(
            "/calls/101/mentor-feedback",
            json=_payload(comment="Первый фидбек"),
        )
        second = await test_client.post(
            "/calls/101/mentor-feedback",
            json=_payload(comment="Повторный фидбек"),
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "Фидбек для этого созвона уже отправлен"
    assert fake_service.responses[101].comment == "Первый фидбек"


@pytest.mark.anyio
async def test_create_mentor_feedback_validation_for_motivation(
    fake_service: FakeMentorFeedbackService,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.post(
            "/calls/101/mentor-feedback",
            json=_payload(motivation=6),
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_mentor_feedback_validation_for_neuromutation_stage(
    fake_service: FakeMentorFeedbackService,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.post(
            "/calls/101/mentor-feedback",
            json=_payload(neuromutation_stage=11),
        )

    assert response.status_code == 422
