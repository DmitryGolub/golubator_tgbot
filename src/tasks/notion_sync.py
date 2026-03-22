import asyncio
import logging

from src.celery_app import celery_app
from src.core.config import settings

logger = logging.getLogger(__name__)


def _run(coro) -> None:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    finally:
        loop.close()
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass


# ── Legacy task (kept for backward compatibility with existing beat) ───


async def _do_legacy_sync() -> None:
    if not settings.NOTION_TOKEN or not settings.NOTION_DATABASE_ID:
        logger.debug("NOTION_TOKEN or NOTION_DATABASE_ID not set, skipping sync")
        return

    from src.services.notion_client import NotionService
    from src.services.notion_sync import NotionSyncService

    notion = NotionService(settings.NOTION_TOKEN, settings.NOTION_DATABASE_ID)
    try:
        sync_service = NotionSyncService(notion)
        result = await sync_service.sync_all()
        logger.info(
            "Notion sync: synced=%d, errors=%d",
            result.synced_users,
            result.errors,
        )
    finally:
        await notion.close()


@celery_app.task(name="notion.sync_cohorts")
def sync_notion_cohorts() -> None:
    _run(_do_legacy_sync())


# ── New bidirectional sync tasks ───────────────────────────────────────


def _get_sync_v2():
    from src.services.notion_sync_v2 import get_sync_service

    return get_sync_service()


@celery_app.task(name="notion.push_changes")
def push_changes() -> None:
    sync = _get_sync_v2()
    if not sync:
        return

    async def _push():
        users = await sync.push_users()
        events = await sync.push_events()
        if users or events:
            logger.info("Push complete: %d users, %d events", users, events)

    _run(_push())


@celery_app.task(name="notion.backup_pull_users")
def backup_pull_users() -> None:
    sync = _get_sync_v2()
    if not sync:
        return
    _run(sync.backup_pull_users())


@celery_app.task(name="notion.backup_pull_events")
def backup_pull_events() -> None:
    sync = _get_sync_v2()
    if not sync:
        return
    _run(sync.backup_pull_events())


