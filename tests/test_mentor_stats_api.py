import os
from typing import Optional
from datetime import datetime

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

from unittest.mock import AsyncMock, patch

from src.api.main import app


@pytest.fixture
def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


STATS_WITH_DATA = {
    "mentor_id": 111,
    "total_calls": 5,
    "total_surveys": 3,
    "avg_mentor_style": 4.33,
    "avg_knowledge_depth": 3.67,
    "avg_understanding": 4.0,
    "avg_satisfaction": 4.0,
}

STATS_EMPTY = {
    "mentor_id": 999,
    "total_calls": 0,
    "total_surveys": 0,
    "avg_mentor_style": None,
    "avg_knowledge_depth": None,
    "avg_understanding": None,
    "avg_satisfaction": None,
}


@pytest.mark.anyio
async def test_mentor_stats_with_data(client: httpx.AsyncClient):
    with patch(
        "src.api.routes.mentor.MentorStatsDAO.get_stats",
        new_callable=AsyncMock,
        return_value=STATS_WITH_DATA,
    ) as mock_get:
        resp = await client.get("/mentors/111/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["mentor_id"] == 111
    assert body["total_calls"] == 5
    assert body["total_surveys"] == 3
    assert body["avg_mentor_style"] == 4.33
    assert body["avg_knowledge_depth"] == 3.67
    assert body["avg_understanding"] == 4.0
    assert body["avg_satisfaction"] == 4.0
    mock_get.assert_awaited_once_with(
        mentor_id=111,
        date_from=None,
        date_to=None,
    )


@pytest.mark.anyio
async def test_mentor_stats_no_calls(client: httpx.AsyncClient):
    with patch(
        "src.api.routes.mentor.MentorStatsDAO.get_stats",
        new_callable=AsyncMock,
        return_value=STATS_EMPTY,
    ):
        resp = await client.get("/mentors/999/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 0
    assert body["total_surveys"] == 0
    assert body["avg_mentor_style"] is None
    assert body["avg_knowledge_depth"] is None
    assert body["avg_understanding"] is None
    assert body["avg_satisfaction"] is None


@pytest.mark.anyio
async def test_mentor_stats_with_date_filter(client: httpx.AsyncClient):
    with patch(
        "src.api.routes.mentor.MentorStatsDAO.get_stats",
        new_callable=AsyncMock,
        return_value=STATS_WITH_DATA,
    ) as mock_get:
        resp = await client.get(
            "/mentors/111/stats",
            params={
                "date_from": "2026-01-01T00:00:00Z",
                "date_to": "2026-03-01T00:00:00Z",
            },
        )

    assert resp.status_code == 200
    mock_get.assert_awaited_once()
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["date_from"] is not None
    assert call_kwargs["date_to"] is not None


@pytest.mark.anyio
async def test_mentor_stats_db_error(client: httpx.AsyncClient):
    from sqlalchemy.exc import OperationalError

    with patch(
        "src.api.routes.mentor.MentorStatsDAO.get_stats",
        new_callable=AsyncMock,
        side_effect=OperationalError("stmt", {}, Exception("conn")),
    ):
        resp = await client.get("/mentors/111/stats")

    assert resp.status_code == 503
