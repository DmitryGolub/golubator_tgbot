from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from notion_client.errors import APIErrorCode, APIResponseError

from src.services.notion.client import NotionClient, NotionPageArchivedError


def _api_error(message: str) -> APIResponseError:
    response = MagicMock()
    response.status_code = 400
    return APIResponseError(
        response=response,
        message=message,
        code=APIErrorCode.ValidationError,
    )


def _build_client(async_page_update: AsyncMock) -> NotionClient:
    client = NotionClient(token="t", database_id="db")
    # Bypass _ensure_client / rate limiter plumbing with a mock SDK client.
    sdk_client = MagicMock()
    sdk_client.pages = MagicMock()
    sdk_client.pages.update = async_page_update

    async def _ensure():
        return sdk_client

    client._ensure_client = _ensure  # type: ignore[assignment]
    client._rate_limiter.acquire = AsyncMock()  # type: ignore[method-assign]
    return client


class TestUpdatePageArchived:
    async def test_raises_archived_error_on_archived_message(self):
        page_update = AsyncMock(
            side_effect=_api_error("Can't edit block that is archived.")
        )
        client = _build_client(page_update)

        with pytest.raises(NotionPageArchivedError) as excinfo:
            await client.update_page("page-1", {"foo": "bar"})

        assert "page-1" in str(excinfo.value)

    async def test_returns_none_on_other_api_error(self, caplog):
        page_update = AsyncMock(side_effect=_api_error("Some other validation error"))
        client = _build_client(page_update)

        with caplog.at_level(logging.ERROR, logger="src.services.notion.client"):
            result = await client.update_page("page-2", {"foo": "bar"})

        assert result is None
        assert any("update_page page-2 failed" in r.message for r in caplog.records)
