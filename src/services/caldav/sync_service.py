"""Orchestrate Meeting → CalDAV one-way sync.

Entry points:
  - `push_meeting(meeting_id)` — upsert the event for every (meeting, account)
    where the account belongs to a participating mentor with sync_enabled.
  - `delete_meeting_events(meeting_id, snapshot)` — delete events from all
    CalDAV servers for a meeting. Accepts a snapshot so it works even after
    the Meeting row is gone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.core.config import settings
from src.core.redis_lock import try_page_lock
from src.dao.caldav_account import CalDAVAccountDAO
from src.dao.caldav_event_link import CalDAVEventLinkDAO, LinkSnapshot
from src.dao.meeting import MeetingDAO
from src.models.caldav import CalDAVAccount
from src.models.meeting import Meeting, ProposalStatus
from src.models.user import User
from src.services.caldav.client import (
    CalDAVAuthError,
    CalDAVClient,
    CalDAVConflictError,
    CalDAVError,
    CalDAVNotFoundError,
    CalDAVTransientError,
)
from src.services.caldav.ical import build_vevent
from src.services.encryption import decrypt

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    account_id: int
    meeting_id: int
    action: str  # "pushed" | "deleted" | "skipped" | "failed"
    error: Optional[str] = None


def _build_uid(meeting_id: int) -> str:
    return f"golubator-meeting-{meeting_id}@{settings.CALDAV_HOSTNAME}"


def _participant_display_name(user: User) -> str:
    name = (user.name or "").strip()
    if name:
        return name
    if user.username:
        return f"@{user.username}"
    return f"id{user.telegram_id}"


def _build_summary(meeting: Meeting, self_telegram_id: int) -> str:
    others = [
        p for p in (meeting.participants or []) if p.telegram_id != self_telegram_id
    ]
    if not others:
        return "Созвон"
    names = ", ".join(_participant_display_name(u) for u in others)
    return f"Созвон с {names}"


class CalDAVSyncService:
    """Stateless push/delete orchestrator for CalDAV."""

    async def push_meeting(self, meeting_id: int) -> list[SyncResult]:
        meeting = await MeetingDAO.get_with_participants(meeting_id)
        if meeting is None:
            logger.info(
                "caldav.push_meeting: meeting not found (likely deleted)",
                extra={"meeting_id": meeting_id},
            )
            return []
        if meeting.scheduled_at is None:
            return []

        # Cancelled meetings delegate to delete.
        if meeting.is_cancelled:
            snapshot = await CalDAVEventLinkDAO.find_by_meeting(meeting_id)
            if not snapshot:
                return []
            return await self.delete_meeting_events(meeting_id, snapshot)

        results: list[SyncResult] = []
        for participant in meeting.participants or []:
            account = await CalDAVAccountDAO.get_for_mentor(participant.telegram_id)
            if account is None or not account.sync_enabled:
                continue
            result = await self._push_for_account(meeting, account)
            results.append(result)
        return results

    async def _push_for_account(
        self, meeting: Meeting, account: CalDAVAccount
    ) -> SyncResult:
        lock_key = f"caldav:lock:{account.id}:{meeting.id}"
        async with try_page_lock(lock_key, ttl=30) as acquired:
            if not acquired:
                logger.debug(
                    "caldav.push: skipped (locked)",
                    extra={"account_id": account.id, "meeting_id": meeting.id},
                )
                return SyncResult(
                    account_id=account.id,
                    meeting_id=meeting.id,
                    action="skipped",
                )
            if not account.default_calendar_url:
                logger.warning(
                    "caldav.push: account has no default_calendar_url",
                    extra={"account_id": account.id, "meeting_id": meeting.id},
                )
                return SyncResult(
                    account_id=account.id,
                    meeting_id=meeting.id,
                    action="failed",
                    error="no calendar configured",
                )

            uid = _build_uid(meeting.id)
            link = await CalDAVEventLinkDAO.get_or_create(
                meeting_id=meeting.id, account_id=account.id, uid=uid
            )
            summary = _build_summary(meeting, account.telegram_id)
            tentative = meeting.proposal_status == ProposalStatus.pending_confirmation
            ics = build_vevent(
                uid=uid,
                summary=summary,
                start=meeting.scheduled_at,
                sequence=(link.sequence or 0) + 1,
                tentative=tentative,
                created_at=meeting.created_at,
                updated_at=meeting.updated_at or meeting.created_at,
            )

            password = decrypt(account.encrypted_password)
            try:
                client = CalDAVClient(
                    base_url=account.base_url,
                    username=account.username,
                    password=password,
                    timeout=settings.CALDAV_HTTP_TIMEOUT_SECONDS,
                )
                try:
                    put = await client.put_event(
                        calendar_url=account.default_calendar_url,
                        uid=uid,
                        ics=ics,
                        etag=link.etag,
                    )
                except CalDAVConflictError:
                    # ETag mismatch — retry without If-Match to overwrite.
                    put = await client.put_event(
                        calendar_url=account.default_calendar_url,
                        uid=uid,
                        ics=ics,
                        etag=None,
                    )
            except CalDAVAuthError as exc:
                await CalDAVAccountDAO.disable(account.id, reason=f"auth failed: {exc}")
                await CalDAVEventLinkDAO.mark_failed(link.id, str(exc))
                logger.warning(
                    "caldav.push: auth failure — account disabled",
                    extra={"account_id": account.id, "meeting_id": meeting.id},
                )
                return SyncResult(
                    account_id=account.id,
                    meeting_id=meeting.id,
                    action="failed",
                    error="auth",
                )
            except CalDAVTransientError:
                await CalDAVAccountDAO.mark_error(account.id, "transient error")
                await CalDAVEventLinkDAO.mark_failed(link.id, "transient")
                raise
            except CalDAVError as exc:
                await CalDAVAccountDAO.mark_error(account.id, str(exc))
                await CalDAVEventLinkDAO.mark_failed(link.id, str(exc))
                return SyncResult(
                    account_id=account.id,
                    meeting_id=meeting.id,
                    action="failed",
                    error=str(exc),
                )
            finally:
                del password

            await CalDAVEventLinkDAO.mark_synced(link.id, href=put.href, etag=put.etag)
            logger.info(
                "caldav.push: synced",
                extra={"account_id": account.id, "meeting_id": meeting.id},
            )
            return SyncResult(
                account_id=account.id, meeting_id=meeting.id, action="pushed"
            )

    async def delete_meeting_events(
        self, meeting_id: int, snapshot: list[LinkSnapshot]
    ) -> list[SyncResult]:
        results: list[SyncResult] = []
        for link in snapshot:
            account = await CalDAVAccountDAO.get_by_id(link.account_id)
            if account is None:
                await CalDAVEventLinkDAO.mark_deleted(link.link_id)
                continue
            result = await self._delete_for_link(meeting_id, account, link)
            results.append(result)
        return results

    async def _delete_for_link(
        self,
        meeting_id: int,
        account: CalDAVAccount,
        link: LinkSnapshot,
    ) -> SyncResult:
        href = link.event_href
        if not href and account.default_calendar_url:
            href = (
                account.default_calendar_url.rstrip("/") + "/" + link.event_uid + ".ics"
            )
        if not href:
            await CalDAVEventLinkDAO.mark_deleted(link.link_id)
            return SyncResult(
                account_id=account.id, meeting_id=meeting_id, action="deleted"
            )

        password = decrypt(account.encrypted_password)
        try:
            client = CalDAVClient(
                base_url=account.base_url,
                username=account.username,
                password=password,
                timeout=settings.CALDAV_HTTP_TIMEOUT_SECONDS,
            )
            try:
                await client.delete_event(href=href, etag=link.etag)
            except CalDAVNotFoundError:
                pass
        except CalDAVAuthError as exc:
            await CalDAVAccountDAO.disable(account.id, reason=f"auth failed: {exc}")
            logger.warning(
                "caldav.delete: auth failure — account disabled",
                extra={"account_id": account.id, "meeting_id": meeting_id},
            )
            return SyncResult(
                account_id=account.id,
                meeting_id=meeting_id,
                action="failed",
                error="auth",
            )
        except CalDAVTransientError:
            await CalDAVAccountDAO.mark_error(account.id, "transient error")
            raise
        except CalDAVError as exc:
            await CalDAVAccountDAO.mark_error(account.id, str(exc))
            return SyncResult(
                account_id=account.id,
                meeting_id=meeting_id,
                action="failed",
                error=str(exc),
            )
        finally:
            del password

        await CalDAVEventLinkDAO.mark_deleted(link.link_id)
        logger.info(
            "caldav.delete: done",
            extra={"account_id": account.id, "meeting_id": meeting_id},
        )
        return SyncResult(
            account_id=account.id, meeting_id=meeting_id, action="deleted"
        )
