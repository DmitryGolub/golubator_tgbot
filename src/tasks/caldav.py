"""Celery tasks for CalDAV sync.

All tasks are no-ops when `CALDAV_ENABLED=False`, so the feature can be
deployed dark and turned on via env.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from src.celery_app import celery_app
from src.core.config import settings
from src.dao.caldav_account import CalDAVAccountDAO
from src.dao.caldav_event_link import CalDAVEventLinkDAO, LinkSnapshot
from src.services.caldav.client import CalDAVClient, CalDAVError, CalDAVTransientError
from src.services.caldav.sync_service import CalDAVSyncService
from src.services.encryption import decrypt
from src.tasks._db import celery_db, get_worker_bot, run_async

logger = logging.getLogger(__name__)


def _caldav_disabled() -> bool:
    if not settings.CALDAV_ENABLED:
        logger.debug("caldav: feature disabled, skipping task")
        return True
    return False


@celery_app.task(
    name="caldav.sync_meeting",
    autoretry_for=(CalDAVTransientError, httpx.HTTPError),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
def sync_meeting(meeting_id: int) -> None:
    if _caldav_disabled():
        return

    async def _run() -> None:
        async with celery_db():
            await CalDAVSyncService().push_meeting(meeting_id)

    run_async(_run())


@celery_app.task(name="caldav.sync_dirty_meetings")
def sync_dirty_meetings() -> None:
    if _caldav_disabled():
        return

    async def _run() -> list[tuple[int, int]]:
        async with celery_db():
            dirty = await CalDAVEventLinkDAO.find_dirty(limit=50)
            return [(d.meeting_id, d.account_id) for d in dirty]

    dirty = run_async(_run())
    if not dirty:
        return
    # Dispatch one task per unique meeting — push_meeting iterates accounts.
    seen: set[int] = set()
    for meeting_id, _ in dirty:
        if meeting_id in seen:
            continue
        seen.add(meeting_id)
        sync_meeting.delay(meeting_id)
    logger.info("caldav.sync_dirty_meetings: dispatched %d meetings", len(seen))


@celery_app.task(name="caldav.verify_account")
def verify_account(account_id: int) -> None:
    if _caldav_disabled():
        return

    async def _run() -> tuple[bool, Optional[str], Optional[int]]:
        async with celery_db():
            account = await CalDAVAccountDAO.get_by_id(account_id)
            if account is None:
                return False, "account not found", None
            password = decrypt(account.encrypted_password)
            try:
                client = CalDAVClient(
                    base_url=account.base_url,
                    username=account.username,
                    password=password,
                    timeout=settings.CALDAV_HTTP_TIMEOUT_SECONDS,
                )
                discovery = await client.verify()
            except CalDAVError as exc:
                await CalDAVAccountDAO.mark_error(account.id, str(exc))
                return False, str(exc), account.telegram_id
            finally:
                del password

            default = discovery.calendars[0] if discovery.calendars else None
            await CalDAVAccountDAO.set_calendars(
                account.id,
                principal_url=discovery.principal_url,
                calendar_home_url=discovery.calendar_home_url,
                default_calendar_url=default.url if default else None,
                calendar_display_name=(default.display_name if default else None),
            )
            await CalDAVAccountDAO.mark_verified(account.id)
            return (
                True,
                default.display_name if default else None,
                account.telegram_id,
            )

    ok, info, telegram_id = run_async(_run())

    if telegram_id is None:
        return

    async def _notify() -> None:
        bot = get_worker_bot()
        if ok:
            name = info or "календарь без названия"
            text = f"✅ Готово. Календарь подключён: <b>{name}</b>."
        else:
            text = (
                "❌ Не удалось подключить календарь.\n"
                f"<i>{info or 'неизвестная ошибка'}</i>\n\n"
                "Проверь URL, логин и пароль приложения."
            )
        try:
            await bot.send_message(telegram_id, text)
        except Exception:
            logger.exception("caldav.verify_account: failed to notify user")

    run_async(_notify())


@celery_app.task(
    name="caldav.delete_events_for_meeting",
    autoretry_for=(CalDAVTransientError, httpx.HTTPError),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
def delete_events_for_meeting(
    meeting_id: int,
    snapshot: list[list],
) -> None:
    """Delete CalDAV events after the Meeting row is (about to be) gone.

    `snapshot` is a list of `[link_id, account_id, event_uid, event_href, etag]`
    tuples captured by the caller before the Meeting is deleted.
    """
    if _caldav_disabled():
        return

    if not snapshot:
        return

    links = [
        LinkSnapshot(
            link_id=row[0],
            account_id=row[1],
            event_uid=row[2],
            event_href=row[3],
            etag=row[4],
        )
        for row in snapshot
    ]

    async def _run() -> None:
        async with celery_db():
            await CalDAVSyncService().delete_meeting_events(meeting_id, links)

    run_async(_run())
