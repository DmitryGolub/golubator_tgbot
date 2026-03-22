import asyncio
import logging

from src.celery_app import celery_app
from src.core.config import settings

logger = logging.getLogger(__name__)


async def _do_sync() -> None:
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


@celery_app.task(name="notion.sync_cohorts")
def sync_notion_cohorts() -> None:
    _run(_do_sync())
