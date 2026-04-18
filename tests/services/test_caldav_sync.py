"""Unit tests for src.services.caldav.sync_service.CalDAVSyncService."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet

from src.core.config import settings
import src.services.encryption as enc
from src.models.meeting import ProposalStatus
from src.services.caldav import sync_service as sync_mod
from src.services.caldav.sync_service import CalDAVSyncService


@pytest.fixture
def enable_caldav(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "CALDAV_ENABLED", True)
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEY", key)
    monkeypatch.setattr(settings, "CALDAV_HOSTNAME", "caldav.example.com")
    monkeypatch.setattr(settings, "CALDAV_HTTP_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEYS_FALLBACK", None)
    enc.reset_fernet_cache()
    yield
    enc.reset_fernet_cache()


def _mentor_user(
    telegram_id: int, name: str, username: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(telegram_id=telegram_id, name=name, username=username)


def _meeting(
    *,
    meeting_id: int,
    mentor_id: int,
    participants,
    proposal_status=ProposalStatus.confirmed,
    is_cancelled: bool = False,
):
    scheduled = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=meeting_id,
        scheduled_at=scheduled,
        created_at=scheduled,
        updated_at=scheduled,
        proposal_status=proposal_status,
        is_cancelled=is_cancelled,
        participants=participants,
        mentor_telegram_id=mentor_id,
    )


@asynccontextmanager
async def _lock_acquired(*a, **kw):
    yield True


@asynccontextmanager
async def _lock_busy(*a, **kw):
    yield False


async def test_push_creates_and_syncs_link(enable_caldav):
    mentor = _mentor_user(100, "Alice")
    other = _mentor_user(200, "Bob")
    meeting = _meeting(meeting_id=42, mentor_id=100, participants=[mentor, other])

    account = SimpleNamespace(
        id=7,
        telegram_id=100,
        sync_enabled=True,
        default_calendar_url="https://caldav.example.com/alice/home",
        base_url="https://caldav.example.com",
        username="alice",
        encrypted_password=enc.encrypt("pw"),
    )
    link = SimpleNamespace(id=1, event_uid="u", sequence=0, etag=None, event_href=None)

    fake_client = AsyncMock()
    fake_client.put_event = AsyncMock(
        return_value=SimpleNamespace(href="https://x/1.ics", etag="abc")
    )

    with (
        patch.object(
            sync_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
        patch.object(
            sync_mod.CalDAVAccountDAO,
            "get_for_mentor",
            AsyncMock(side_effect=lambda tg: account if tg == 100 else None),
        ),
        patch.object(
            sync_mod.CalDAVEventLinkDAO,
            "get_or_create",
            AsyncMock(return_value=link),
        ),
        patch.object(
            sync_mod.CalDAVEventLinkDAO, "mark_synced", AsyncMock()
        ) as mark_synced,
        patch.object(sync_mod, "try_page_lock", _lock_acquired),
        patch.object(sync_mod, "CalDAVClient", lambda **kw: fake_client),
    ):
        results = await CalDAVSyncService().push_meeting(42)

    assert len(results) == 1
    assert results[0].action == "pushed"
    mark_synced.assert_awaited_once()
    fake_client.put_event.assert_awaited_once()
    # UID and summary checks
    ics = fake_client.put_event.await_args.kwargs["ics"]
    assert b"golubator-meeting-42@caldav.example.com" in ics
    assert "Созвон с Bob".encode("utf-8") in ics


async def test_summary_prefers_telegram_username(enable_caldav):
    mentor = _mentor_user(100, "Alice")
    # Bob has both a Notion-card name and a Telegram username — username wins.
    other = _mentor_user(200, "Bob From Notion", username="Conte145")
    meeting = _meeting(meeting_id=42, mentor_id=100, participants=[mentor, other])

    account = SimpleNamespace(
        id=7,
        telegram_id=100,
        sync_enabled=True,
        default_calendar_url="https://caldav.example.com/alice/home",
        base_url="https://caldav.example.com",
        username="alice",
        encrypted_password=enc.encrypt("pw"),
    )
    link = SimpleNamespace(id=1, event_uid="u", sequence=0, etag=None, event_href=None)
    fake_client = AsyncMock()
    fake_client.put_event = AsyncMock(return_value=SimpleNamespace(href="h", etag="e"))

    with (
        patch.object(
            sync_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
        patch.object(
            sync_mod.CalDAVAccountDAO,
            "get_for_mentor",
            AsyncMock(side_effect=lambda tg: account if tg == 100 else None),
        ),
        patch.object(
            sync_mod.CalDAVEventLinkDAO,
            "get_or_create",
            AsyncMock(return_value=link),
        ),
        patch.object(sync_mod.CalDAVEventLinkDAO, "mark_synced", AsyncMock()),
        patch.object(sync_mod, "try_page_lock", _lock_acquired),
        patch.object(sync_mod, "CalDAVClient", lambda **kw: fake_client),
    ):
        await CalDAVSyncService().push_meeting(42)

    ics = fake_client.put_event.await_args.kwargs["ics"]
    assert "Созвон с @Conte145".encode("utf-8") in ics
    # The Notion-card name must not leak when a username is available.
    assert "Bob From Notion".encode("utf-8") not in ics


async def test_pending_sets_tentative_status(enable_caldav):
    mentor = _mentor_user(100, "Alice")
    other = _mentor_user(200, "Bob")
    meeting = _meeting(
        meeting_id=42,
        mentor_id=100,
        participants=[mentor, other],
        proposal_status=ProposalStatus.pending_confirmation,
    )
    account = SimpleNamespace(
        id=7,
        telegram_id=100,
        sync_enabled=True,
        default_calendar_url="https://caldav.example.com/alice/home",
        base_url="https://caldav.example.com",
        username="alice",
        encrypted_password=enc.encrypt("pw"),
    )
    link = SimpleNamespace(id=1, event_uid="u", sequence=0, etag=None, event_href=None)

    fake_client = AsyncMock()
    fake_client.put_event = AsyncMock(return_value=SimpleNamespace(href="h", etag="e"))

    with (
        patch.object(
            sync_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
        patch.object(
            sync_mod.CalDAVAccountDAO,
            "get_for_mentor",
            AsyncMock(side_effect=lambda tg: account if tg == 100 else None),
        ),
        patch.object(
            sync_mod.CalDAVEventLinkDAO,
            "get_or_create",
            AsyncMock(return_value=link),
        ),
        patch.object(sync_mod.CalDAVEventLinkDAO, "mark_synced", AsyncMock()),
        patch.object(sync_mod, "try_page_lock", _lock_acquired),
        patch.object(sync_mod, "CalDAVClient", lambda **kw: fake_client),
    ):
        await CalDAVSyncService().push_meeting(42)

    ics = fake_client.put_event.await_args.kwargs["ics"]
    assert b"STATUS:TENTATIVE" in ics
    assert b"STATUS:CONFIRMED" not in ics


async def test_cancelled_meeting_deletes(enable_caldav):
    mentor = _mentor_user(100, "Alice")
    meeting = _meeting(
        meeting_id=42,
        mentor_id=100,
        participants=[mentor],
        is_cancelled=True,
    )
    account = SimpleNamespace(
        id=7,
        telegram_id=100,
        sync_enabled=True,
        default_calendar_url="https://caldav.example.com/alice/home",
        base_url="https://caldav.example.com",
        username="alice",
        encrypted_password=enc.encrypt("pw"),
    )
    snapshot = [
        sync_mod.LinkSnapshot(
            link_id=1,
            account_id=7,
            event_uid="u",
            event_href="https://caldav.example.com/alice/home/u.ics",
            etag="e",
        )
    ]

    fake_client = AsyncMock()
    fake_client.delete_event = AsyncMock(return_value=None)

    with (
        patch.object(
            sync_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
        patch.object(
            sync_mod.CalDAVEventLinkDAO,
            "find_by_meeting",
            AsyncMock(return_value=snapshot),
        ),
        patch.object(
            sync_mod.CalDAVAccountDAO,
            "get_by_id",
            AsyncMock(return_value=account),
        ),
        patch.object(sync_mod.CalDAVEventLinkDAO, "mark_deleted", AsyncMock()),
        patch.object(sync_mod, "CalDAVClient", lambda **kw: fake_client),
    ):
        results = await CalDAVSyncService().push_meeting(42)

    fake_client.delete_event.assert_awaited_once()
    assert any(r.action == "deleted" for r in results)


async def test_lock_busy_skips(enable_caldav):
    mentor = _mentor_user(100, "Alice")
    other = _mentor_user(200, "Bob")
    meeting = _meeting(meeting_id=42, mentor_id=100, participants=[mentor, other])
    account = SimpleNamespace(
        id=7,
        telegram_id=100,
        sync_enabled=True,
        default_calendar_url="https://caldav.example.com/alice/home",
        base_url="https://caldav.example.com",
        username="alice",
        encrypted_password=enc.encrypt("pw"),
    )

    fake_client = AsyncMock()
    fake_client.put_event = AsyncMock(return_value=SimpleNamespace(href="h", etag="e"))

    with (
        patch.object(
            sync_mod.MeetingDAO,
            "get_with_participants",
            AsyncMock(return_value=meeting),
        ),
        patch.object(
            sync_mod.CalDAVAccountDAO,
            "get_for_mentor",
            AsyncMock(side_effect=lambda tg: account if tg == 100 else None),
        ),
        patch.object(sync_mod, "try_page_lock", _lock_busy),
        patch.object(sync_mod, "CalDAVClient", lambda **kw: fake_client),
    ):
        results = await CalDAVSyncService().push_meeting(42)

    assert results == [
        sync_mod.SyncResult(account_id=7, meeting_id=42, action="skipped")
    ]
    fake_client.put_event.assert_not_awaited()
