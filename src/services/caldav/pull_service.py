"""Orchestrate CalDAV → PostgreSQL pull for a single account.

The service runs once per account on the Celery beat tick:
  1. acquire a non-blocking per-account Redis lock,
  2. detect changes (RFC 6578 sync-collection, with calendar-query fallback),
  3. apply each change idempotently via `CalDAVReverseSyncService`,
  4. persist the new sync_token / ctag on success.

`bootstrap` mode (sync_token is NULL) only seeds per-link `remote_*` and
`etag` fields without firing cancel/reschedule actions — it brings new
accounts up to a known baseline without spamming participants.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.core.config import settings
from src.core.redis_lock import try_page_lock
from src.dao.caldav_account import CalDAVAccountDAO
from src.dao.caldav_event_link import CalDAVEventLinkDAO
from src.dao.meeting import MeetingDAO
from src.models.caldav import CalDAVAccount
from src.services.caldav.client import (
    CalDAVAuthError,
    CalDAVClient,
    CalDAVError,
    CalDAVNotFoundError,
    CalDAVTransientError,
    ChangedEvent,
)
from src.services.caldav.parser import (
    extract_meeting_id,
    extract_uid_from_href,
    parse_vevent,
)
from src.services.caldav.reverse_sync_service import CalDAVReverseSyncService
from src.services.encryption import decrypt

logger = logging.getLogger(__name__)

UID_PREFIX = "golubator-meeting-"


@dataclass
class PullResult:
    account_id: int
    applied: int = 0
    skipped_echo: int = 0
    skipped_lww: int = 0
    ignored_foreign: int = 0
    cancelled: int = 0
    rescheduled: int = 0
    bootstrap: bool = False
    error: Optional[str] = None


class CalDAVPullService:
    """Stateless pull orchestrator. One instance per pull tick is fine."""

    def __init__(self, reverse_sync: Optional[CalDAVReverseSyncService] = None) -> None:
        self._reverse = reverse_sync or CalDAVReverseSyncService()

    async def pull_account(self, account_id: int) -> PullResult:
        result = PullResult(account_id=account_id)

        async with try_page_lock(f"caldav:pull:{account_id}", ttl=120) as acquired:
            if not acquired:
                logger.debug(
                    "caldav.pull: skipped (locked)", extra={"account_id": account_id}
                )
                return result

            account = await CalDAVAccountDAO.get_by_id(account_id)
            if account is None:
                result.error = "account not found"
                return result
            if not account.sync_enabled:
                return result
            if not account.default_calendar_url:
                logger.warning(
                    "caldav.pull: account has no default_calendar_url",
                    extra={"account_id": account_id},
                )
                return result

            password = decrypt(account.encrypted_password)
            try:
                client = CalDAVClient(
                    base_url=account.base_url,
                    username=account.username,
                    password=password,
                    timeout=settings.CALDAV_HTTP_TIMEOUT_SECONDS,
                )
                try:
                    (
                        new_sync_token,
                        new_ctag,
                        changes,
                        bootstrap,
                    ) = await self._detect_changes(client, account)
                except CalDAVAuthError as exc:
                    await CalDAVAccountDAO.disable(
                        account.id, reason=f"auth failed: {exc}"
                    )
                    await CalDAVAccountDAO.mark_pull_error(account.id, str(exc))
                    result.error = "auth"
                    return result
                except CalDAVTransientError as exc:
                    await CalDAVAccountDAO.mark_pull_error(account.id, str(exc))
                    raise
                except CalDAVError as exc:
                    await CalDAVAccountDAO.mark_pull_error(account.id, str(exc))
                    result.error = str(exc)
                    return result

                result.bootstrap = bootstrap

                for change in changes:
                    try:
                        await self._apply_change(
                            client, account, change, bootstrap, result
                        )
                    except Exception:
                        logger.exception(
                            "caldav.pull: per-event error, continuing",
                            extra={
                                "account_id": account_id,
                                "href": change.href,
                            },
                        )

                await CalDAVAccountDAO.mark_pulled(
                    account.id,
                    sync_token=new_sync_token,
                    ctag=new_ctag,
                    last_pulled_at=datetime.now(timezone.utc),
                )
                logger.info(
                    "caldav.pull: done",
                    extra={
                        "account_id": account_id,
                        "applied": result.applied,
                        "cancelled": result.cancelled,
                        "rescheduled": result.rescheduled,
                        "skipped_echo": result.skipped_echo,
                        "skipped_lww": result.skipped_lww,
                        "ignored_foreign": result.ignored_foreign,
                        "bootstrap": result.bootstrap,
                    },
                )
                return result
            finally:
                del password

    # ── change detection ───────────────────────────────────────────────

    async def _detect_changes(
        self, client: CalDAVClient, account: CalDAVAccount
    ) -> tuple[Optional[str], Optional[str], list[ChangedEvent], bool]:
        """Return (new_sync_token, new_ctag, changes, bootstrap)."""
        # Fast path: incremental via sync-collection.
        if account.sync_token:
            sync_result = await client.sync_collection(
                account.default_calendar_url, account.sync_token
            )
            if not sync_result.invalid_token:
                return (
                    sync_result.new_sync_token or account.sync_token,
                    account.ctag,
                    sync_result.changes,
                    False,
                )
            logger.info(
                "caldav.pull: invalid sync_token, falling back to full-scan",
                extra={"account_id": account.id},
            )

        # Bootstrap or fallback: synthesize changes via calendar-query + diff
        # against the per-account known links.
        new_ctag = None
        try:
            new_ctag = await client.get_ctag(account.default_calendar_url)
        except CalDAVError as exc:
            logger.warning(
                "caldav.pull: getctag failed, continuing without ctag: %s", exc
            )

        objects = await client.calendar_query(account.default_calendar_url, UID_PREFIX)
        seen_hrefs = {o.href for o in objects}

        # We don't have a real new sync_token from calendar-query; try to
        # establish one for next tick by issuing an initial sync-collection
        # (token=None) — many servers respond with the current token.
        new_sync_token: Optional[str] = None
        try:
            init_sync = await client.sync_collection(account.default_calendar_url, None)
            if init_sync.new_sync_token and not init_sync.invalid_token:
                new_sync_token = init_sync.new_sync_token
        except CalDAVError as exc:
            logger.debug("caldav.pull: initial sync-collection failed: %s", exc)

        changes: list[ChangedEvent] = [
            ChangedEvent(href=o.href, etag=o.etag, change_type="changed")
            for o in objects
        ]

        existing_links = await CalDAVEventLinkDAO.find_by_account(account.id)
        for link in existing_links:
            if link.event_href and link.event_href not in seen_hrefs:
                changes.append(
                    ChangedEvent(
                        href=link.event_href, etag=link.etag, change_type="deleted"
                    )
                )

        bootstrap = account.sync_token is None
        return new_sync_token, new_ctag, changes, bootstrap

    # ── per-event application ──────────────────────────────────────────

    async def _apply_change(
        self,
        client: CalDAVClient,
        account: CalDAVAccount,
        change: ChangedEvent,
        bootstrap: bool,
        result: PullResult,
    ) -> None:
        link = await CalDAVEventLinkDAO.find_by_account_and_href_or_uid(
            account.id, href=change.href, uid=None
        )

        uid_guess: Optional[str] = None
        if link is None:
            # href mismatch (iCloud percent-encodes `@`, Radicale doesn't, etc.)
            # — try matching by the UID embedded in the href's filename.
            uid_guess = extract_uid_from_href(change.href)
            if uid_guess:
                link = await CalDAVEventLinkDAO.find_by_account_and_href_or_uid(
                    account.id, href=None, uid=uid_guess
                )
                if link is not None and link.event_href != change.href:
                    # Heal the stale href so the next pull is O(1) by href.
                    await CalDAVEventLinkDAO.update_href(link.id, change.href)
                    logger.info(
                        "caldav.pull: healed event_href via UID fallback",
                        extra={
                            "account_id": account.id,
                            "link_id": link.id,
                            "old_href": link.event_href,
                            "new_href": change.href,
                            "uid": uid_guess,
                        },
                    )

        if change.change_type == "deleted":
            if link is None:
                logger.info(
                    "caldav.pull: ignored deletion — no link match",
                    extra={
                        "account_id": account.id,
                        "href": change.href,
                        "uid_guess": uid_guess,
                        "reason": "no_link",
                    },
                )
                result.ignored_foreign += 1
                return
            if bootstrap:
                await CalDAVEventLinkDAO.mark_deleted(link.id)
                return
            await self._reverse.cancel_from_caldav(
                meeting_id=link.meeting_id, source_account_id=account.id
            )
            await CalDAVEventLinkDAO.mark_deleted(link.id)
            result.cancelled += 1
            result.applied += 1
            return

        # change_type == "changed"
        if link is not None and change.etag and change.etag == link.etag:
            logger.info(
                "caldav.pull: skipped_echo by etag",
                extra={
                    "account_id": account.id,
                    "meeting_id": link.meeting_id,
                    "href": change.href,
                    "etag": change.etag,
                },
            )
            result.skipped_echo += 1
            return

        try:
            ics, server_etag = await client.get_event(change.href)
        except CalDAVNotFoundError:
            # Race: server deleted the object between report and GET — treat
            # as deleted on the next pull tick.
            return

        parsed = parse_vevent(ics)
        meeting_id = extract_meeting_id(parsed.uid) if parsed else None
        if parsed is None or meeting_id is None:
            logger.info(
                "caldav.pull: ignored — UID not ours",
                extra={
                    "account_id": account.id,
                    "href": change.href,
                    "uid": parsed.uid if parsed else None,
                    "reason": "invalid_uid",
                },
            )
            result.ignored_foreign += 1
            return

        if link is None:
            # We never pushed this UID from this account → not ours to manage.
            logger.info(
                "caldav.pull: ignored — no link for UID",
                extra={
                    "account_id": account.id,
                    "href": change.href,
                    "uid": parsed.uid,
                    "uid_guess": uid_guess,
                    "reason": "no_link",
                },
            )
            result.ignored_foreign += 1
            return

        if parsed.has_rrule:
            logger.warning(
                "caldav.pull: skipping recurring event (RRULE/RDATE)",
                extra={"account_id": account.id, "uid": parsed.uid},
            )
            return

        # Slow anti-echo: identical LAST-MODIFIED+SEQUENCE seen previously.
        if (
            link.remote_last_modified == parsed.last_modified
            and link.remote_sequence == parsed.sequence
            and link.remote_last_modified is not None
        ):
            logger.info(
                "caldav.pull: skipped_echo by last_modified+sequence",
                extra={
                    "account_id": account.id,
                    "meeting_id": meeting_id,
                    "last_modified": parsed.last_modified.isoformat(),
                    "sequence": parsed.sequence,
                    "link_etag": link.etag,
                    "change_etag": change.etag,
                },
            )
            result.skipped_echo += 1
            return

        meeting = await MeetingDAO.get_with_participants(meeting_id)
        if meeting is None:
            logger.info(
                "caldav.pull: ignored — meeting gone",
                extra={
                    "account_id": account.id,
                    "meeting_id": meeting_id,
                    "href": change.href,
                    "reason": "no_meeting",
                },
            )
            result.ignored_foreign += 1
            return

        # Last-write-wins: if server's LAST-MODIFIED is older than our
        # Meeting.updated_at, our domain is more recent — skip the action,
        # but still record what we observed so we don't redo the comparison.
        if (
            parsed.last_modified is not None
            and meeting.updated_at is not None
            and parsed.last_modified <= _aware(meeting.updated_at)
        ):
            logger.info(
                "caldav.pull: skipped_lww — domain newer than server",
                extra={
                    "account_id": account.id,
                    "meeting_id": meeting_id,
                    "server_last_modified": parsed.last_modified.isoformat(),
                    "meeting_updated_at": meeting.updated_at.isoformat(),
                    "link_etag": link.etag,
                    "change_etag": change.etag,
                },
            )
            await CalDAVEventLinkDAO.update_after_pull(
                link.id,
                etag=server_etag or change.etag or link.etag,
                remote_last_modified=parsed.last_modified,
                remote_sequence=parsed.sequence,
                mark_pushed=False,
            )
            result.skipped_lww += 1
            return

        if bootstrap:
            await CalDAVEventLinkDAO.update_after_pull(
                link.id,
                etag=server_etag or change.etag or link.etag,
                remote_last_modified=parsed.last_modified,
                remote_sequence=parsed.sequence,
                mark_pushed=False,
            )
            return

        if parsed.status == "CANCELLED":
            await self._reverse.cancel_from_caldav(
                meeting_id=meeting_id, source_account_id=account.id
            )
            await CalDAVEventLinkDAO.update_after_pull(
                link.id,
                etag=server_etag or change.etag or link.etag,
                remote_last_modified=parsed.last_modified,
                remote_sequence=parsed.sequence,
                mark_pushed=True,
            )
            result.cancelled += 1
            result.applied += 1
            return

        if parsed.dtstart is None or _close_enough(
            parsed.dtstart, meeting.scheduled_at
        ):
            logger.info(
                "caldav.pull: no-op — dtstart unchanged",
                extra={
                    "account_id": account.id,
                    "meeting_id": meeting_id,
                    "server_dtstart": (
                        parsed.dtstart.isoformat() if parsed.dtstart else None
                    ),
                    "meeting_scheduled_at": (
                        meeting.scheduled_at.isoformat()
                        if meeting.scheduled_at
                        else None
                    ),
                },
            )
            await CalDAVEventLinkDAO.update_after_pull(
                link.id,
                etag=server_etag or change.etag or link.etag,
                remote_last_modified=parsed.last_modified,
                remote_sequence=parsed.sequence,
                mark_pushed=False,
            )
            return

        await self._reverse.reschedule_from_caldav(
            meeting_id=meeting_id,
            new_scheduled_at=parsed.dtstart,
            source_account_id=account.id,
        )
        await CalDAVEventLinkDAO.update_after_pull(
            link.id,
            etag=server_etag or change.etag or link.etag,
            remote_last_modified=parsed.last_modified,
            remote_sequence=parsed.sequence,
            mark_pushed=True,
        )
        result.rescheduled += 1
        result.applied += 1


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _close_enough(a: Optional[datetime], b: Optional[datetime]) -> bool:
    if a is None or b is None:
        return False
    delta = abs((_aware(a) - _aware(b)).total_seconds())
    return delta <= 1.0
