import logging

from src.celery_app import celery_app
from src.services.notion.client import NotionDatabaseUnavailableError
from src.tasks._db import run_async

logger = logging.getLogger(__name__)


# ── Bidirectional sync tasks ───────────────────────────────────────


def _get_sync_v2():
    from src.services.notion_sync_v2 import get_sync_service

    return get_sync_service()


@celery_app.task(name="notion.push_changes")
def push_changes() -> None:
    sync = _get_sync_v2()
    if not sync:
        return

    async def _push():
        mentors = await sync.push_mentors()
        mentees = await sync.push_mentees()
        events = await sync.push_events()
        if mentors or mentees or events:
            logger.info(
                "Push complete: %d mentors, %d mentees, %d events",
                mentors,
                mentees,
                events,
            )

    try:
        run_async(_push())
    except NotionDatabaseUnavailableError as exc:
        logger.warning("push_changes skipped: %s", exc)


@celery_app.task(name="notion.backup_pull_users")
def backup_pull_users() -> None:
    sync = _get_sync_v2()
    if not sync:
        return

    async def _pull():
        mentors = await sync.backup_pull_mentors()
        mentees = await sync.backup_pull_mentees()
        if mentors or mentees:
            logger.info(
                "Backup pull complete: %d mentors, %d mentees", mentors, mentees
            )

    try:
        run_async(_pull())
    except NotionDatabaseUnavailableError as exc:
        logger.warning("backup_pull_users skipped: %s", exc)


@celery_app.task(name="notion.backup_pull_events")
def backup_pull_events() -> None:
    sync = _get_sync_v2()
    if not sync:
        return
    try:
        run_async(sync.backup_pull_events())
    except NotionDatabaseUnavailableError as exc:
        logger.warning("backup_pull_events skipped: %s", exc)


@celery_app.task(name="notion.backup_pull_cohorts")
def backup_pull_cohorts() -> None:
    sync = _get_sync_v2()
    if not sync:
        return
    try:
        run_async(sync.backup_pull_cohorts())
    except NotionDatabaseUnavailableError as exc:
        logger.warning("backup_pull_cohorts skipped: %s", exc)
