"""Unit tests for src.tasks.caldav beat/dispatch logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import settings
from src.dao.caldav_event_link import DirtyLink
from src.tasks import caldav as caldav_tasks


@pytest.fixture(autouse=True)
def enable_caldav(monkeypatch):
    monkeypatch.setattr(settings, "CALDAV_ENABLED", True)


def test_sync_dirty_meetings_dispatches_unique(monkeypatch):
    dirty = [
        DirtyLink(meeting_id=1, account_id=7),
        DirtyLink(meeting_id=1, account_id=8),  # duplicate meeting, different account
        DirtyLink(meeting_id=2, account_id=7),
    ]

    async def _fake_find(limit: int = 50):
        return dirty

    monkeypatch.setattr(
        caldav_tasks.CalDAVEventLinkDAO,
        "find_dirty",
        AsyncMock(side_effect=_fake_find),
    )

    delay_mock = MagicMock()
    monkeypatch.setattr(caldav_tasks.sync_meeting, "delay", delay_mock)

    def _run(coro):
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(caldav_tasks, "run_async", _run)

    caldav_tasks.sync_dirty_meetings()

    # Unique meeting IDs dispatched exactly once each.
    dispatched = {call.args[0] for call in delay_mock.call_args_list}
    assert dispatched == {1, 2}
    assert delay_mock.call_count == 2


def test_sync_dirty_meetings_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "CALDAV_ENABLED", False)
    delay_mock = MagicMock()
    monkeypatch.setattr(caldav_tasks.sync_meeting, "delay", delay_mock)

    # find_dirty should not be invoked at all.
    find_mock = AsyncMock()
    monkeypatch.setattr(caldav_tasks.CalDAVEventLinkDAO, "find_dirty", find_mock)

    caldav_tasks.sync_dirty_meetings()

    find_mock.assert_not_awaited()
    delay_mock.assert_not_called()


def test_sync_meeting_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "CALDAV_ENABLED", False)
    run_mock = MagicMock()
    monkeypatch.setattr(caldav_tasks, "run_async", run_mock)
    caldav_tasks.sync_meeting(1)
    run_mock.assert_not_called()
