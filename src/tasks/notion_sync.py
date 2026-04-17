import logging

from src.celery_app import celery_app
from src.services.notion.client import NotionDatabaseUnavailableError
from src.services.notion_sync_v2 import sync_service_scope
from src.tasks._db import celery_db, run_async

logger = logging.getLogger(__name__)


# ── Bidirectional sync tasks ───────────────────────────────────────


@celery_app.task(name="notion.push_changes")
def push_changes() -> None:
    async def _push():
        async with sync_service_scope() as sync:
            if sync is None:
                return
            async with celery_db():
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
def backup_pull_users(suppress_emit: bool = False) -> None:
    async def _pull():
        async with sync_service_scope() as sync:
            if sync is None:
                return
            async with celery_db():
                mentors = await sync.backup_pull_mentors()
                mentees = await sync.backup_pull_mentees(suppress_emit=suppress_emit)
                if mentors or mentees:
                    logger.info(
                        "Backup pull complete: %d mentors, %d mentees",
                        mentors,
                        mentees,
                    )

    try:
        run_async(_pull())
    except NotionDatabaseUnavailableError as exc:
        logger.warning("backup_pull_users skipped: %s", exc)


@celery_app.task(name="notion.backup_pull_events")
def backup_pull_events() -> None:
    async def _pull():
        async with sync_service_scope() as sync:
            if sync is None:
                return
            async with celery_db():
                await sync.backup_pull_events()

    try:
        run_async(_pull())
    except NotionDatabaseUnavailableError as exc:
        logger.warning("backup_pull_events skipped: %s", exc)


@celery_app.task(name="notion.backup_pull_cohorts")
def backup_pull_cohorts(suppress_emit: bool = False) -> None:
    async def _pull():
        async with sync_service_scope() as sync:
            if sync is None:
                return
            async with celery_db():
                await sync.backup_pull_cohorts(suppress_emit=suppress_emit)

    try:
        run_async(_pull())
    except NotionDatabaseUnavailableError as exc:
        logger.warning("backup_pull_cohorts skipped: %s", exc)
