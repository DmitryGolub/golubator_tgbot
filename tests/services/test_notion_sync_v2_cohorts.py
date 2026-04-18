from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.services.notion_sync_v2 import NotionSyncServiceV2


def _data(categories=(), tags=(), status=None, intern=None, last_edited_time=None):
    return SimpleNamespace(
        categories=list(categories),
        tags=list(tags),
        status=status,
        intern=intern,
        last_edited_time=last_edited_time,
    )


def _svc() -> NotionSyncServiceV2:
    return NotionSyncServiceV2(mentor_repo=None, mentee_repo=None, event_repo=None)


class TestSyncCohortsNoChange:
    async def test_noop_when_state_matches(self):
        svc = _svc()
        data = _data(categories=["Data"], status="Active")

        session = AsyncMock()
        session.add = MagicMock()

        select_result = MagicMock()
        select_result.all.return_value = [
            (1, "Category", "Data"),
            (2, "Status", "Active"),
        ]
        session.execute = AsyncMock(return_value=select_result)

        diffs = await svc._sync_cohorts(session, 100, data, datetime.now(timezone.utc))

        assert diffs == []
        # Only the initial SELECT was executed — no upsert, no DELETE, no INSERT.
        assert session.execute.await_count == 1
        session.add.assert_not_called()


class TestSyncCohortsAdded:
    async def test_all_new_cohorts(self):
        svc = _svc()
        data = _data(categories=["Data"], status="Active")

        session = AsyncMock()
        session.add = MagicMock()

        empty_old = MagicMock()
        empty_old.all.return_value = []

        id_result = MagicMock()
        id_result.all.return_value = [
            (1, "Category", "Data"),
            (2, "Status", "Active"),
        ]

        # execute order: SELECT old, bulk upsert Cohort, SELECT ids.
        session.execute = AsyncMock(side_effect=[empty_old, MagicMock(), id_result])

        diffs = await svc._sync_cohorts(session, 100, data, datetime.now(timezone.utc))

        assert len(diffs) == 2
        assert all(d["user_telegram_id"] == 100 for d in diffs)
        assert all(d["old_value"] is None for d in diffs)
        assert {d["new_value"] for d in diffs} == {"Data", "Active"}

        # 2 UserCohort + 2 StageTransition (each diff has non-None new_value).
        assert session.add.call_count == 4
        # No DELETE — old_entries is empty.
        assert session.execute.await_count == 3


class TestSyncCohortsMix:
    async def test_add_and_remove(self):
        svc = _svc()
        # New state keeps nothing from old — one added, one removed.
        data = _data(categories=["Data"])

        session = AsyncMock()
        session.add = MagicMock()

        old_result = MagicMock()
        old_result.all.return_value = [(9, "Category", "Product")]

        id_result = MagicMock()
        id_result.all.return_value = [(1, "Category", "Data")]

        # execute order: SELECT old, bulk upsert Cohort, SELECT ids, DELETE removed.
        session.execute = AsyncMock(
            side_effect=[old_result, MagicMock(), id_result, MagicMock()]
        )

        diffs = await svc._sync_cohorts(session, 100, data, datetime.now(timezone.utc))

        added = [d for d in diffs if d["new_value"] is not None]
        removed = [d for d in diffs if d["new_value"] is None]
        assert len(added) == 1
        assert len(removed) == 1
        assert added[0]["new_value"] == "Data"
        # Single old value for the category — surfaced as old_value.
        assert added[0]["old_value"] == "Product"
        assert removed[0]["old_value"] == "Product"

        # One UserCohort (Data) + one StageTransition (only for the added diff).
        assert session.add.call_count == 2
        assert session.execute.await_count == 4
