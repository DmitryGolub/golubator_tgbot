"""Unit tests for CalDAVPullService — fully mocked, no I/O."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from src.core.config import settings
import src.services.encryption as enc
from src.services.caldav import pull_service as pull_mod
from src.services.caldav.client import (
    CalDAVNotFoundError,
    ChangedEvent,
    SyncCollectionResult,
)
from src.services.caldav.pull_service import CalDAVPullService


@pytest.fixture
def caldav_env(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "CALDAV_ENABLED", True)
    monkeypatch.setattr(settings, "CALDAV_PULL_ENABLED", True)
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEY", key)
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEYS_FALLBACK", None)
    monkeypatch.setattr(settings, "CALDAV_HTTP_TIMEOUT_SECONDS", 5)
    enc.reset_fernet_cache()
    yield
    enc.reset_fernet_cache()


def _account(account_id: int = 7, telegram_id: int = 100, sync_token=None):
    return SimpleNamespace(
        id=account_id,
        telegram_id=telegram_id,
        sync_enabled=True,
        default_calendar_url="https://x/cal/",
        base_url="https://x",
        username="u",
        encrypted_password=enc.encrypt("pw"),
        sync_token=sync_token,
        ctag=None,
    )


def _link(
    *,
    link_id: int = 1,
    meeting_id: int = 42,
    account_id: int = 7,
    href: str = "/cal/golubator-meeting-42.ics",
    etag: str | None = "old-etag",
    remote_last_modified: datetime | None = None,
    remote_sequence: int | None = None,
):
    return SimpleNamespace(
        id=link_id,
        meeting_id=meeting_id,
        account_id=account_id,
        event_uid="golubator-meeting-42@x",
        event_href=href,
        etag=etag,
        sequence=0,
        remote_last_modified=remote_last_modified,
        remote_sequence=remote_sequence,
    )


def _meeting(*, scheduled_at: datetime, updated_at: datetime, is_cancelled=False):
    return SimpleNamespace(
        id=42,
        scheduled_at=scheduled_at,
        updated_at=updated_at,
        is_cancelled=is_cancelled,
        participants=[],
    )


@asynccontextmanager
async def _lock_acquired(*a, **kw):
    yield True


@asynccontextmanager
async def _lock_busy(*a, **kw):
    yield False


def _make_client_factory(client_mock):
    def factory(**_):
        return client_mock

    return factory


# ──────────────────────────────────────────────────────────────────────


async def test_lock_busy_returns_zero(caldav_env):
    with patch.object(pull_mod, "try_page_lock", _lock_busy):
        result = await CalDAVPullService().pull_account(7)
    assert result.applied == 0
    assert result.error is None


async def test_foreign_uid_ignored(caldav_env):
    account = _account(sync_token="tok-1")
    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[
            ChangedEvent(
                href="/cal/foreign.ics", etag="e-foreign", change_type="changed"
            )
        ],
        invalid_token=False,
    )
    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)
    client.get_event = AsyncMock(
        return_value=(
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//y//EN\r\n"
            b"BEGIN:VEVENT\r\nUID:foreign-event@y\r\n"
            b"DTSTART:20260101T120000Z\r\nDTSTAMP:20260101T100000Z\r\n"
            b"END:VEVENT\r\nEND:VCALENDAR\r\n",
            "e-foreign",
        )
    )

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(
            pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()
        ) as mark_pulled,
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=None),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    assert result.ignored_foreign == 1
    assert result.applied == 0
    reverse.cancel_from_caldav.assert_not_awaited()
    reverse.reschedule_from_caldav.assert_not_awaited()
    mark_pulled.assert_awaited_once()


async def test_etag_echo_skipped(caldav_env):
    account = _account(sync_token="tok-1")
    link = _link(etag="same-etag")
    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[
            ChangedEvent(href=link.event_href, etag="same-etag", change_type="changed")
        ],
        invalid_token=False,
    )
    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)
    client.get_event = AsyncMock()
    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=link),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    assert result.skipped_echo == 1
    assert result.applied == 0
    client.get_event.assert_not_awaited()
    reverse.cancel_from_caldav.assert_not_awaited()


def _ours_ics(*, dtstart: str, last_mod: str, sequence: int = 1, status="CONFIRMED"):
    text = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//x//y//EN\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:golubator-meeting-42@x\r\n"
        f"DTSTART:{dtstart}\r\n"
        f"LAST-MODIFIED:{last_mod}\r\n"
        "DTSTAMP:20260101T100000Z\r\n"
        f"SEQUENCE:{sequence}\r\n"
        f"STATUS:{status}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return text.encode("utf-8")


async def test_lww_skip_when_meeting_newer(caldav_env):
    account = _account(sync_token="tok-1")
    link = _link(etag="old-etag")
    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[
            ChangedEvent(href=link.event_href, etag="new-etag", change_type="changed")
        ],
        invalid_token=False,
    )
    # LAST-MODIFIED is 2026-04-10; meeting.updated_at is 2026-04-15 → server is older.
    ics = _ours_ics(dtstart="20260601T120000Z", last_mod="20260410T120000Z")
    meeting = _meeting(
        scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)
    client.get_event = AsyncMock(return_value=(ics, "new-etag"))

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=link),
        ),
        patch.object(
            pull_mod.CalDAVEventLinkDAO, "update_after_pull", AsyncMock()
        ) as update,
        patch.object(
            pull_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    assert result.skipped_lww == 1
    reverse.reschedule_from_caldav.assert_not_awaited()
    # remote_* still updated, but mark_pushed=False
    update.assert_awaited_once()
    assert update.await_args.kwargs["mark_pushed"] is False


async def test_deleted_invokes_cancel(caldav_env):
    account = _account(sync_token="tok-1")
    link = _link()
    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[ChangedEvent(href=link.event_href, etag=None, change_type="deleted")],
        invalid_token=False,
    )
    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=link),
        ),
        patch.object(
            pull_mod.CalDAVEventLinkDAO, "mark_deleted", AsyncMock()
        ) as mark_deleted,
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    assert result.cancelled == 1
    assert result.applied == 1
    reverse.cancel_from_caldav.assert_awaited_once_with(
        meeting_id=42, source_account_id=7
    )
    mark_deleted.assert_awaited_once()


async def test_dtstart_changed_triggers_reschedule(caldav_env):
    account = _account(sync_token="tok-1")
    link = _link(etag="old-etag")
    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[
            ChangedEvent(href=link.event_href, etag="new-etag", change_type="changed")
        ],
        invalid_token=False,
    )
    new_dtstart_iso = "20260601T140000Z"
    new_dtstart = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
    ics = _ours_ics(dtstart=new_dtstart_iso, last_mod="20260420T120000Z")
    meeting = _meeting(
        scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )

    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)
    client.get_event = AsyncMock(return_value=(ics, "new-etag"))

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=link),
        ),
        patch.object(
            pull_mod.CalDAVEventLinkDAO, "update_after_pull", AsyncMock()
        ) as update,
        patch.object(
            pull_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    assert result.rescheduled == 1
    assert result.applied == 1
    reverse.reschedule_from_caldav.assert_awaited_once_with(
        meeting_id=42, new_scheduled_at=new_dtstart, source_account_id=7
    )
    update.assert_awaited_once()
    assert update.await_args.kwargs["mark_pushed"] is True


async def test_status_cancelled_invokes_cancel(caldav_env):
    account = _account(sync_token="tok-1")
    link = _link(etag="old-etag")
    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[
            ChangedEvent(href=link.event_href, etag="new-etag", change_type="changed")
        ],
        invalid_token=False,
    )
    ics = _ours_ics(
        dtstart="20260501T120000Z", last_mod="20260420T120000Z", status="CANCELLED"
    )
    meeting = _meeting(
        scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)
    client.get_event = AsyncMock(return_value=(ics, "new-etag"))

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=link),
        ),
        patch.object(pull_mod.CalDAVEventLinkDAO, "update_after_pull", AsyncMock()),
        patch.object(
            pull_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    assert result.cancelled == 1
    assert result.applied == 1
    reverse.cancel_from_caldav.assert_awaited_once()


async def test_invalid_token_falls_back_to_calendar_query(caldav_env):
    account = _account(sync_token="tok-stale")
    link = _link(etag="old-etag")
    invalid_sync = SyncCollectionResult(
        new_sync_token="", changes=[], invalid_token=True
    )
    init_sync = SyncCollectionResult(
        new_sync_token="tok-fresh", changes=[], invalid_token=False
    )

    client = MagicMock()
    client.sync_collection = AsyncMock(side_effect=[invalid_sync, init_sync])
    client.get_ctag = AsyncMock(return_value="ct-1")
    cal_obj = SimpleNamespace(
        href=link.event_href,
        etag="new-etag",
        calendar_data=_ours_ics(
            dtstart="20260501T120000Z", last_mod="20260301T100000Z"
        ),
    )
    client.calendar_query = AsyncMock(return_value=[cal_obj])
    client.get_event = AsyncMock(return_value=(cal_obj.calendar_data, "new-etag"))

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(
            pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()
        ) as mark_pulled,
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account",
            AsyncMock(return_value=[link]),
        ),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=link),
        ),
        patch.object(pull_mod.CalDAVEventLinkDAO, "update_after_pull", AsyncMock()),
        patch.object(
            pull_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(
                return_value=_meeting(
                    scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
                )
            ),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    # invalid_token forced full-scan; not bootstrap because account.sync_token was set.
    assert result.bootstrap is False
    client.calendar_query.assert_awaited_once()
    mark_pulled.assert_awaited_once()
    # The new sync_token from the fresh init-sync was persisted.
    assert mark_pulled.await_args.kwargs["sync_token"] == "tok-fresh"


async def test_bootstrap_seeds_remote_fields_without_actions(caldav_env):
    account = _account(sync_token=None)
    link = _link(etag="old-etag")
    init_sync = SyncCollectionResult(
        new_sync_token="tok-init", changes=[], invalid_token=False
    )

    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=init_sync)
    client.get_ctag = AsyncMock(return_value="ct-1")
    cal_obj = SimpleNamespace(
        href=link.event_href,
        etag="server-etag",
        calendar_data=_ours_ics(
            dtstart="20260501T120000Z", last_mod="20260301T100000Z"
        ),
    )
    client.calendar_query = AsyncMock(return_value=[cal_obj])
    client.get_event = AsyncMock(return_value=(cal_obj.calendar_data, "server-etag"))

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account",
            AsyncMock(return_value=[link]),
        ),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=link),
        ),
        patch.object(
            pull_mod.CalDAVEventLinkDAO, "update_after_pull", AsyncMock()
        ) as update,
        patch.object(
            pull_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(
                return_value=_meeting(
                    scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
                )
            ),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    assert result.bootstrap is True
    assert result.applied == 0
    reverse.cancel_from_caldav.assert_not_awaited()
    reverse.reschedule_from_caldav.assert_not_awaited()
    update.assert_awaited_once()
    assert update.await_args.kwargs["mark_pushed"] is False


async def test_partial_failure_continues(caldav_env):
    account = _account(sync_token="tok-1")
    link_ok = _link(link_id=1, href="/cal/ok.ics", etag="old")
    link_bad = _link(link_id=2, href="/cal/bad.ics", etag="old")

    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[
            ChangedEvent(href="/cal/bad.ics", etag="x", change_type="changed"),
            ChangedEvent(href="/cal/ok.ics", etag=None, change_type="deleted"),
        ],
        invalid_token=False,
    )

    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)
    client.get_event = AsyncMock(side_effect=RuntimeError("boom"))

    async def find_link(account_id, *, href, uid):
        if href == "/cal/bad.ics":
            return link_bad
        if href == "/cal/ok.ics":
            return link_ok
        return None

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(
            pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()
        ) as mark_pulled,
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(side_effect=find_link),
        ),
        patch.object(pull_mod.CalDAVEventLinkDAO, "mark_deleted", AsyncMock()),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    # The deleted event still applies; the changed one swallowed the error.
    assert result.cancelled == 1
    reverse.cancel_from_caldav.assert_awaited_once()
    mark_pulled.assert_awaited_once()


async def test_href_encoding_mismatch_recovered_via_uid_fallback(caldav_env):
    """Server href contains `%40` but DB stored literal `@` — fallback by UID."""
    account = _account(sync_token="tok-1")
    # Link was saved with literal `@` in href (old behaviour).
    link = _link(
        etag="old-etag",
        href="https://x/cal/golubator-meeting-42@x.ics",
    )
    # Server now reports the same event with percent-encoded `@`.
    server_href = "https://x/cal/golubator-meeting-42%40x.ics"
    new_dtstart = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
    ics = _ours_ics(dtstart="20260601T140000Z", last_mod="20260420T120000Z")
    meeting = _meeting(
        scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )
    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[
            ChangedEvent(href=server_href, etag="new-etag", change_type="changed")
        ],
        invalid_token=False,
    )
    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)
    client.get_event = AsyncMock(return_value=(ics, "new-etag"))

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    async def find_link(account_id, *, href, uid):
        # First lookup by href fails (encoding mismatch),
        # second lookup by UID succeeds.
        if href == server_href and uid is None:
            return None
        if href is None and uid == "golubator-meeting-42@x":
            return link
        return None

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(side_effect=find_link),
        ),
        patch.object(
            pull_mod.CalDAVEventLinkDAO, "update_href", AsyncMock()
        ) as update_href,
        patch.object(pull_mod.CalDAVEventLinkDAO, "update_after_pull", AsyncMock()),
        patch.object(
            pull_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    assert result.rescheduled == 1
    assert result.applied == 1
    assert result.ignored_foreign == 0
    update_href.assert_awaited_once_with(link.id, server_href)
    reverse.reschedule_from_caldav.assert_awaited_once_with(
        meeting_id=42, new_scheduled_at=new_dtstart, source_account_id=7
    )


async def test_get_event_404_during_changed_is_ignored(caldav_env):
    account = _account(sync_token="tok-1")
    link = _link(etag="old-etag")
    sync_result = SyncCollectionResult(
        new_sync_token="tok-2",
        changes=[
            ChangedEvent(href=link.event_href, etag="new-etag", change_type="changed")
        ],
        invalid_token=False,
    )
    client = MagicMock()
    client.sync_collection = AsyncMock(return_value=sync_result)
    client.get_event = AsyncMock(side_effect=CalDAVNotFoundError("gone"))

    reverse = MagicMock()
    reverse.cancel_from_caldav = AsyncMock()
    reverse.reschedule_from_caldav = AsyncMock()

    with (
        patch.object(pull_mod, "try_page_lock", _lock_acquired),
        patch.object(pull_mod, "CalDAVClient", _make_client_factory(client)),
        patch.object(
            pull_mod.CalDAVAccountDAO, "get_by_id", AsyncMock(return_value=account)
        ),
        patch.object(pull_mod.CalDAVAccountDAO, "mark_pulled", AsyncMock()),
        patch.object(
            pull_mod.CalDAVEventLinkDAO,
            "find_by_account_and_href_or_uid",
            AsyncMock(return_value=link),
        ),
    ):
        result = await CalDAVPullService(reverse_sync=reverse).pull_account(7)

    # 404 on GET is treated as no-op for now; deletion will be picked up next tick.
    assert result.applied == 0
    reverse.cancel_from_caldav.assert_not_awaited()
