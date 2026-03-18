import os
from datetime import datetime, timezone
from types import SimpleNamespace
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
from src.models.user import Role, State


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.anyio
async def test_create_tag(client: httpx.AsyncClient) -> None:
    with patch(
        "src.api.routes.user.TagDAO.add",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(id=1, name="vip"),
    ) as mock_add:
        response = await client.post("/tags", json={"name": "vip"})

    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "vip"}
    mock_add.assert_awaited_once_with(name="vip")


@pytest.mark.anyio
async def test_assign_tag_to_user(client: httpx.AsyncClient) -> None:
    user = SimpleNamespace(
        telegram_id=1001,
        username="user1",
        name="User One",
        role=Role.student,
        state=State.greeting,
        registered_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        tags=[SimpleNamespace(id=1, name="vip")],
    )
    with patch(
        "src.api.routes.user.UserDAO.assign_tag",
        new_callable=AsyncMock,
        return_value=user,
    ) as mock_assign:
        response = await client.post("/users/1001/tags/1")

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 1001
    assert response.json()["tags"] == [{"id": 1, "name": "vip"}]
    mock_assign.assert_awaited_once_with(telegram_id=1001, tag_id=1)


@pytest.mark.anyio
async def test_list_users_with_filters(client: httpx.AsyncClient) -> None:
    user = SimpleNamespace(
        telegram_id=1001,
        username="user1",
        name="User One",
        role=Role.student,
        state=State.study,
        registered_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        tags=[SimpleNamespace(id=2, name="active")],
    )
    with patch(
        "src.api.routes.user.UserDAO.get_all",
        new_callable=AsyncMock,
        return_value=[user],
    ) as mock_get_all:
        response = await client.get(
            "/users",
            params={
                "role": "student",
                "state": "study",
                "tag_id": 2,
                "registered_from": "2026-03-01T00:00:00Z",
                "registered_to": "2026-03-31T00:00:00Z",
            },
        )

    assert response.status_code == 200
    assert len(response.json()) == 1
    mock_get_all.assert_awaited_once()
    kwargs = mock_get_all.call_args.kwargs
    assert kwargs["role"] == Role.student
    assert kwargs["state"] == State.study
    assert kwargs["tag_id"] == 2


@pytest.mark.anyio
async def test_list_users_invalid_date_range(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/users",
        params={
            "registered_from": "2026-03-31T00:00:00Z",
            "registered_to": "2026-03-01T00:00:00Z",
        },
    )
    assert response.status_code == 422
