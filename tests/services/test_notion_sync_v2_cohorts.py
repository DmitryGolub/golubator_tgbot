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


class TestSyncCohortsPreloadedSnapshot:
    async def test_noop_with_preloaded_snapshot_no_select(self):
        """When old_ids_by_entry is passed and matches payload, no SQL runs."""
        svc = _svc()
        data = _data(categories=["Data"], status="Active")

        session = AsyncMock()
        session.add = MagicMock()
        session.execute = AsyncMock()

        diffs = await svc._sync_cohorts(
            session,
            100,
            data,
            datetime.now(timezone.utc),
            old_ids_by_entry={("Category", "Data"): 1, ("Status", "Active"): 2},
        )

        assert diffs == []
        # No snapshot SELECT — caller pre-supplied the snapshot.
        session.execute.assert_not_called()
        session.add.assert_not_called()

    async def test_added_with_preloaded_snapshot(self):
        """Snapshot passed in → first SQL is the bulk upsert, not the snapshot SELECT."""
        svc = _svc()
        data = _data(categories=["Data", "Product"])

        session = AsyncMock()
        session.add = MagicMock()

        id_result = MagicMock()
        id_result.all.return_value = [(1, "Category", "Product")]
        # execute order: bulk upsert Cohort, SELECT ids — no snapshot SELECT.
        session.execute = AsyncMock(side_effect=[MagicMock(), id_result])

        diffs = await svc._sync_cohorts(
            session,
            100,
            data,
            datetime.now(timezone.utc),
            old_ids_by_entry={("Category", "Data"): 1},
        )

        added = [d for d in diffs if d["new_value"] is not None]
        assert len(added) == 1
        assert added[0]["new_value"] == "Product"
        # Exactly 2 SQL round-trips: upsert + id resolve. No snapshot SELECT.
        assert session.execute.await_count == 2


class TestBackupPullCohortsBatch:
    def _mentee_row(self, page_id, telegram_id, synced_at):
        return SimpleNamespace(
            notion_page_id=page_id,
            telegram_id=telegram_id,
            synced_at=synced_at,
        )

    async def test_empty_batch_no_queries(self, monkeypatch):
        """Empty mentees payload → single commit, no SELECTs."""
        svc = _svc()
        svc.mentee_repo = MagicMock()
        svc.mentee_repo.get_all = AsyncMock(return_value=[])

        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        factory_cm = MagicMock()
        factory_cm.__aenter__ = AsyncMock(return_value=session)
        factory_cm.__aexit__ = AsyncMock(return_value=None)
        factory = MagicMock(return_value=factory_cm)

        engine = MagicMock()
        engine.dispose = AsyncMock()

        monkeypatch.setattr(
            "src.services.notion_sync_v2._make_session_factory",
            lambda: (engine, factory),
        )

        count = await svc.backup_pull_cohorts(suppress_emit=True)

        assert count == 0
        # No SQL at all — not even the batch prefetch (empty page_ids).
        session.execute.assert_not_called()
        session.commit.assert_awaited_once()

    async def test_echo_skip_does_not_hit_sync_cohorts(self, monkeypatch):
        """Three mentees; two have fresh synced_at → echo-skipped without _sync_cohorts."""
        svc = _svc()
        svc.mentee_repo = MagicMock()

        now = datetime.now(timezone.utc)
        fresh = _data(categories=["Data"], last_edited_time=now)
        stale_payload = _data(
            categories=["Data"],
            last_edited_time=now,
        )
        stale_payload.page_id = "p3"
        fresh_a = _data(categories=["Data"], last_edited_time=now)
        fresh_a.page_id = "p1"
        fresh_b = _data(categories=["Data"], last_edited_time=now)
        fresh_b.page_id = "p2"
        stale_payload.page_id = "p3"
        # Re-use fresh binding for clarity.
        del fresh
        svc.mentee_repo.get_all = AsyncMock(
            return_value=[fresh_a, fresh_b, stale_payload]
        )

        prefetch_rows = MagicMock()
        prefetch_rows.all.return_value = [
            # fresh_a, fresh_b: synced_at already covers last_edited_time.
            self._mentee_row("p1", 101, now),
            self._mentee_row("p2", 102, now),
            # stale: needs sync.
            self._mentee_row("p3", 103, None),
        ]
        snap_result = MagicMock()
        snap_result.all.return_value = []  # no existing cohorts for user 103

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()

        # Stub _sync_cohorts to observe calls without doing real SQL.
        sync_mock = AsyncMock(return_value=[])
        monkeypatch.setattr(svc, "_sync_cohorts", sync_mock)

        # Mock session.begin_nested as async context manager.
        nested_cm = MagicMock()
        nested_cm.__aenter__ = AsyncMock(return_value=None)
        nested_cm.__aexit__ = AsyncMock(return_value=None)
        session.begin_nested = MagicMock(return_value=nested_cm)

        session.execute.side_effect = [prefetch_rows, snap_result]

        factory_cm = MagicMock()
        factory_cm.__aenter__ = AsyncMock(return_value=session)
        factory_cm.__aexit__ = AsyncMock(return_value=None)
        factory = MagicMock(return_value=factory_cm)
        engine = MagicMock()
        engine.dispose = AsyncMock()
        monkeypatch.setattr(
            "src.services.notion_sync_v2._make_session_factory",
            lambda: (engine, factory),
        )

        count = await svc.backup_pull_cohorts(suppress_emit=True)

        # Only the stale one got synced; two fresh were echo-skipped.
        assert count == 1
        assert sync_mock.await_count == 1
        call = sync_mock.await_args
        assert call.args[1] == 103
        # Preloaded snapshot is passed — no per-user SELECT.
        assert "old_ids_by_entry" in call.kwargs
        # Exactly 2 batch SELECTs (Mentee prefetch + UserCohort JOIN).
        assert session.execute.await_count == 2
