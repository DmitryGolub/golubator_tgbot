import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

# Required for settings initialization during imports
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")

from src.api.dependencies import get_survey_service
from src.api.main import app
from src.api.schemas.survey import SurveyQuestion, SurveyQuestionOption, SurveyStatus, SurveySubmitRequest
from src.services.survey import CallNotFoundError, SurveyNotAvailableError


@dataclass
class FakeSurveyResponse:
    call_id: int
    student_id: int
    duration_option: str
    mentor_style: int
    knowledge_depth: int
    understanding: int
    comment: str | None
    created_at: datetime


class FakeSurveyService:
    def __init__(self) -> None:
        self.calls: dict[int, SurveyStatus] = {
            101: SurveyStatus.available,
            202: SurveyStatus.available,
            303: SurveyStatus.not_available,
        }
        self.responses: dict[int, FakeSurveyResponse] = {}

    @staticmethod
    def build_questions() -> list[SurveyQuestion]:
        return [
            SurveyQuestion(
                id="duration_option",
                title="Длительность созвона",
                kind="choice",
                required=True,
                options=[
                    SurveyQuestionOption(value="lt_30", label="<30 минут"),
                    SurveyQuestionOption(value="30_45", label="30-45 минут"),
                    SurveyQuestionOption(value="45_60", label="45-60 минут"),
                    SurveyQuestionOption(value="gt_60", label=">60 минут"),
                ],
            ),
            SurveyQuestion(
                id="mentor_style",
                title="Стиль общения ментора",
                kind="rating",
                required=True,
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="knowledge_depth",
                title="Глубина проверки знаний",
                kind="rating",
                required=True,
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="understanding",
                title="Насколько ученик понял материал",
                kind="rating",
                required=True,
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="comment",
                title="Комментарий",
                kind="text",
                required=False,
            ),
        ]

    async def get_survey_state(self, call_id: int) -> tuple[SurveyStatus, FakeSurveyResponse | None]:
        if call_id not in self.calls:
            raise CallNotFoundError

        if call_id in self.responses:
            return SurveyStatus.completed, self.responses[call_id]

        return self.calls[call_id], None

    async def submit_survey(
        self,
        *,
        call_id: int,
        payload: SurveySubmitRequest,
    ) -> tuple[FakeSurveyResponse, bool]:
        if call_id not in self.calls:
            raise CallNotFoundError

        if self.calls[call_id] != SurveyStatus.available and call_id not in self.responses:
            raise SurveyNotAvailableError

        if call_id in self.responses:
            return self.responses[call_id], True

        response = FakeSurveyResponse(
            call_id=call_id,
            student_id=999,
            duration_option=payload.duration_option.value,
            mentor_style=payload.mentor_style,
            knowledge_depth=payload.knowledge_depth,
            understanding=payload.understanding,
            comment=payload.comment,
            created_at=datetime(2026, 2, 18, 12, 0, tzinfo=timezone.utc),
        )
        self.responses[call_id] = response
        return response, False


@pytest.fixture
def fake_service() -> FakeSurveyService:
    service = FakeSurveyService()

    async def _override_service() -> FakeSurveyService:
        return service

    app.dependency_overrides[get_survey_service] = _override_service
    yield service
    app.dependency_overrides.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "duration_option": "45_60",
        "mentor_style": 5,
        "knowledge_depth": 4,
        "understanding": 5,
        "comment": "Отличный разбор",
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_successful_full_survey_flow(fake_service: FakeSurveyService) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        get_before = await test_client.get("/calls/101/survey")
        assert get_before.status_code == 200
        assert get_before.json()["status"] == "available"
        assert [q["id"] for q in get_before.json()["questions"]] == [
            "duration_option",
            "mentor_style",
            "knowledge_depth",
            "understanding",
            "comment",
        ]

        submit = await test_client.post("/calls/101/survey", json=_payload())
        assert submit.status_code == 200
        body = submit.json()
        assert body["already_submitted"] is False
        assert body["response"]["call_id"] == 101
        assert body["response"]["comment"] == "Отличный разбор"

        get_after = await test_client.get("/calls/101/survey")
        assert get_after.status_code == 200
        assert get_after.json()["status"] == "completed"
        assert get_after.json()["response"]["duration_option"] == "45_60"


@pytest.mark.anyio
async def test_rating_validation_1_5(fake_service: FakeSurveyService) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.post("/calls/101/survey", json=_payload(mentor_style=6))

    assert response.status_code == 422


@pytest.mark.anyio
async def test_response_is_bound_to_specific_call_id(fake_service: FakeSurveyService) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        submit = await test_client.post("/calls/101/survey", json=_payload())
        assert submit.status_code == 200

        second_call = await test_client.get("/calls/202/survey")
        assert second_call.status_code == 200
        assert second_call.json()["status"] == "available"
        assert second_call.json()["response"] is None


@pytest.mark.anyio
async def test_duplicate_submit_is_idempotent(fake_service: FakeSurveyService) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        first = await test_client.post("/calls/101/survey", json=_payload(comment="Первый ответ"))
        second = await test_client.post("/calls/101/survey", json=_payload(comment="Повторный ответ"))

    assert first.status_code == 200
    assert first.json()["already_submitted"] is False

    assert second.status_code == 200
    assert second.json()["already_submitted"] is True
    assert second.json()["response"]["comment"] == "Первый ответ"


@pytest.mark.anyio
async def test_call_id_out_of_range_returns_422(fake_service: FakeSurveyService) -> None:
    transport = httpx.ASGITransport(app=app)
    too_large_call_id = 9999999999999

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        get_response = await test_client.get(f"/calls/{too_large_call_id}/survey")
        post_response = await test_client.post(f"/calls/{too_large_call_id}/survey", json=_payload())

    assert get_response.status_code == 422
    assert post_response.status_code == 422


@pytest.mark.anyio
async def test_sqlalchemy_error_mapped_to_503() -> None:
    class FailingSurveyService:
        @staticmethod
        def build_questions() -> list[SurveyQuestion]:
            return []

        async def get_survey_state(self, call_id: int) -> tuple[SurveyStatus, None]:
            raise SQLAlchemyError("db unavailable")

        async def submit_survey(
            self,
            *,
            call_id: int,
            payload: SurveySubmitRequest,
        ) -> tuple[FakeSurveyResponse, bool]:
            raise SQLAlchemyError("db unavailable")

    async def _override_service() -> FailingSurveyService:
        return FailingSurveyService()

    app.dependency_overrides[get_survey_service] = _override_service
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
            get_response = await test_client.get("/calls/101/survey")
            post_response = await test_client.post("/calls/101/survey", json=_payload())
    finally:
        app.dependency_overrides.clear()

    assert get_response.status_code == 503
    assert post_response.status_code == 503


@pytest.mark.anyio
async def test_asyncpg_error_mapped_to_503() -> None:
    asyncpg = pytest.importorskip("asyncpg")

    class FailingSurveyService:
        @staticmethod
        def build_questions() -> list[SurveyQuestion]:
            return []

        async def get_survey_state(self, call_id: int) -> tuple[SurveyStatus, None]:
            raise asyncpg.exceptions.InvalidCatalogNameError("database does not exist")

        async def submit_survey(
            self,
            *,
            call_id: int,
            payload: SurveySubmitRequest,
        ) -> tuple[FakeSurveyResponse, bool]:
            raise asyncpg.exceptions.InvalidCatalogNameError("database does not exist")

    async def _override_service() -> FailingSurveyService:
        return FailingSurveyService()

    app.dependency_overrides[get_survey_service] = _override_service
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
            get_response = await test_client.get("/calls/101/survey")
            post_response = await test_client.post("/calls/101/survey", json=_payload())
    finally:
        app.dependency_overrides.clear()

    assert get_response.status_code == 503
    assert post_response.status_code == 503
