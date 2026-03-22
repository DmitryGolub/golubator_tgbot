import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")

from src.api.main import app
from src.services.feedback_export import (
    FEEDBACK_EXPORT_HEADERS,
    FeedbackExportDataset,
    FeedbackExportResult,
    FeedbackExportRow,
)
from src.services.yandex_sheets import YandexSheetTarget


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


def _dataset() -> FeedbackExportDataset:
    row = FeedbackExportRow(
        call_id=101,
        call_started_at=datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
        mentor_id=1001,
        mentor_name="Ментор",
        student_id=2002,
        student_name="Ученик",
        student_survey_status="completed",
        student_survey_created_at=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
        mentor_feedback_status="completed",
        mentor_feedback_created_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
    )
    return FeedbackExportDataset(headers=FEEDBACK_EXPORT_HEADERS, rows=[row])


@pytest.mark.anyio
async def test_export_feedback_dry_run_response(client: httpx.AsyncClient) -> None:
    result = FeedbackExportResult(dataset=_dataset(), dry_run=True)

    with patch(
        "src.api.routes.export_feedback.FeedbackExportService.run_export",
        new_callable=AsyncMock,
        return_value=result,
    ) as mock_run_export:
        response = await client.post(
            "/export_feedback",
            params={
                "dry_run": "true",
                "date_from": "2026-03-01T00:00:00Z",
                "date_to": "2026-03-31T00:00:00Z",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "dry_run"
    assert body["rows_count"] == 1
    assert body["headers"] == list(FEEDBACK_EXPORT_HEADERS)
    assert body["sample_rows"][0]["call_id"] == 101
    assert body["sample_rows"][0]["mentor_name"] == "Ментор"
    mock_run_export.assert_awaited_once()
    kwargs = mock_run_export.call_args.kwargs
    assert kwargs["dry_run"] is True
    assert kwargs["date_from"] == datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
    assert kwargs["date_to"] == datetime(2026, 3, 31, 0, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_export_feedback_export_response(client: httpx.AsyncClient) -> None:
    result = FeedbackExportResult(
        dataset=_dataset(),
        dry_run=False,
        target=YandexSheetTarget(
            file_path="/analytics/feedback_export.xlsx",
            sheet_name="feedback_export",
        ),
    )

    with patch(
        "src.api.routes.export_feedback.FeedbackExportService.run_export",
        new_callable=AsyncMock,
        return_value=result,
    ):
        response = await client.post("/export_feedback")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "exported"
    assert body["rows_count"] == 1
    assert body["target_file_path"] == "/analytics/feedback_export.xlsx"
    assert body["sheet_name"] == "feedback_export"


@pytest.mark.anyio
async def test_export_feedback_rejects_invalid_date_range(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/export_feedback",
        params={
            "date_from": "2026-03-31T00:00:00Z",
            "date_to": "2026-03-01T00:00:00Z",
        },
    )

    assert response.status_code == 422
