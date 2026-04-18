from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, delete, or_, select, update

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.caldav import CalDAVAccount, CalDAVEventLink, CalDAVSyncStatus
from src.models.meeting import Meeting


@dataclass(frozen=True)
class DirtyLink:
    meeting_id: int
    account_id: int


@dataclass(frozen=True)
class LinkSnapshot:
    link_id: int
    account_id: int
    event_uid: str
    event_href: Optional[str]
    etag: Optional[str]


class CalDAVEventLinkDAO(BaseDAO):
    model = CalDAVEventLink

    @classmethod
    async def get_or_create(
        cls, *, meeting_id: int, account_id: int, uid: str
    ) -> CalDAVEventLink:
        async with async_session_maker() as session:
            existing = await session.execute(
                select(CalDAVEventLink).where(
                    and_(
                        CalDAVEventLink.meeting_id == meeting_id,
                        CalDAVEventLink.account_id == account_id,
                    )
                )
            )
            link = existing.scalars().one_or_none()
            if link is not None:
                return link
            link = CalDAVEventLink(
                meeting_id=meeting_id,
                account_id=account_id,
                event_uid=uid,
                status=CalDAVSyncStatus.pending,
            )
            session.add(link)
            await session.commit()
            await session.refresh(link)
            return link

    @classmethod
    async def mark_synced(
        cls,
        link_id: int,
        *,
        href: Optional[str],
        etag: Optional[str],
    ) -> None:
        async with async_session_maker() as session:
            res = await session.execute(
                select(CalDAVEventLink).where(CalDAVEventLink.id == link_id)
            )
            link = res.scalars().one_or_none()
            if link is None:
                return
            link.event_href = href
            link.etag = etag
            link.status = CalDAVSyncStatus.synced
            link.sequence = (link.sequence or 0) + 1
            link.last_pushed_at = datetime.now(timezone.utc)
            link.last_error = None
            link.last_error_at = None
            link.retry_count = 0
            await session.commit()

    @classmethod
    async def mark_failed(cls, link_id: int, error: str) -> None:
        async with async_session_maker() as session:
            await session.execute(
                update(CalDAVEventLink)
                .where(CalDAVEventLink.id == link_id)
                .values(
                    status=CalDAVSyncStatus.failed,
                    last_error=error[:2000],
                    last_error_at=datetime.now(timezone.utc),
                    retry_count=CalDAVEventLink.retry_count + 1,
                )
            )
            await session.commit()

    @classmethod
    async def mark_deleted(cls, link_id: int) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(CalDAVEventLink).where(CalDAVEventLink.id == link_id)
            )
            await session.commit()

    @classmethod
    async def find_dirty(cls, limit: int = 50) -> list[DirtyLink]:
        """Return `(meeting_id, account_id)` tuples that need a push.

        Dirty = (no link yet) OR (meeting.updated_at > link.last_pushed_at)
        OR (link status = failed). Only active accounts are considered.
        """
        async with async_session_maker() as session:
            query = (
                select(Meeting.id, CalDAVAccount.id)
                .join(
                    CalDAVAccount,
                    CalDAVAccount.telegram_id == Meeting.mentor_telegram_id,
                )
                .outerjoin(
                    CalDAVEventLink,
                    and_(
                        CalDAVEventLink.meeting_id == Meeting.id,
                        CalDAVEventLink.account_id == CalDAVAccount.id,
                    ),
                )
                .where(
                    and_(
                        CalDAVAccount.sync_enabled.is_(True),
                        Meeting.is_cancelled.is_(False),
                        Meeting.scheduled_at.is_not(None),
                        or_(
                            CalDAVEventLink.id.is_(None),
                            CalDAVEventLink.last_pushed_at.is_(None),
                            Meeting.updated_at > CalDAVEventLink.last_pushed_at,
                            CalDAVEventLink.status == CalDAVSyncStatus.failed,
                        ),
                    )
                )
                .limit(limit)
            )
            result = await session.execute(query)
            return [
                DirtyLink(meeting_id=row[0], account_id=row[1]) for row in result.all()
            ]

    @classmethod
    async def find_by_meeting(cls, meeting_id: int) -> list[LinkSnapshot]:
        """Return all links for a meeting — used to snapshot before DELETE."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(CalDAVEventLink).where(CalDAVEventLink.meeting_id == meeting_id)
            )
            links = result.scalars().all()
            return [
                LinkSnapshot(
                    link_id=link.id,
                    account_id=link.account_id,
                    event_uid=link.event_uid,
                    event_href=link.event_href,
                    etag=link.etag,
                )
                for link in links
            ]

    @classmethod
    async def get_with_account(
        cls, link_id: int
    ) -> tuple[CalDAVEventLink, CalDAVAccount] | None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(CalDAVEventLink, CalDAVAccount)
                .join(CalDAVAccount, CalDAVAccount.id == CalDAVEventLink.account_id)
                .where(CalDAVEventLink.id == link_id)
            )
            row = result.one_or_none()
            return (row[0], row[1]) if row else None

    @classmethod
    async def find_by_account(cls, account_id: int) -> list[CalDAVEventLink]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(CalDAVEventLink).where(CalDAVEventLink.account_id == account_id)
            )
            return list(result.scalars().all())

    @classmethod
    async def find_by_account_and_href_or_uid(
        cls,
        account_id: int,
        *,
        href: Optional[str],
        uid: Optional[str],
    ) -> Optional[CalDAVEventLink]:
        if not href and not uid:
            return None
        conditions = []
        if href:
            conditions.append(CalDAVEventLink.event_href == href)
        if uid:
            conditions.append(CalDAVEventLink.event_uid == uid)
        async with async_session_maker() as session:
            result = await session.execute(
                select(CalDAVEventLink).where(
                    and_(
                        CalDAVEventLink.account_id == account_id,
                        or_(*conditions),
                    )
                )
            )
            return result.scalars().first()

    @classmethod
    async def update_after_pull(
        cls,
        link_id: int,
        *,
        etag: Optional[str],
        remote_last_modified: Optional[datetime],
        remote_sequence: Optional[int],
        mark_pushed: bool = True,
    ) -> None:
        now = datetime.now(timezone.utc)
        values: dict = {
            "etag": etag,
            "remote_last_modified": remote_last_modified,
            "remote_sequence": remote_sequence,
            "last_pulled_at": now,
            "status": CalDAVSyncStatus.synced,
        }
        if mark_pushed:
            values["last_pushed_at"] = now
        async with async_session_maker() as session:
            await session.execute(
                update(CalDAVEventLink)
                .where(CalDAVEventLink.id == link_id)
                .values(**values)
            )
            await session.commit()
