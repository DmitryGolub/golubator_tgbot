import logging
import time
from datetime import datetime, timedelta, timezone

from src.celery_app import celery_app
from src.core.redis import get_redis
from src.services.notion.client import NotionDatabaseUnavailableError
from src.services.notion_sync_v2 import sync_service_scope
from src.tasks._db import celery_db, run_async

logger = logging.getLogger(__name__)

_COHORTS_LAST_RUN_KEY = "notion:backup_pull_cohorts:last_run"
# Re-fetch a few minutes of overlap to absorb Notion replication lag and clock skew.
_COHORTS_OVERLAP = timedelta(minutes=3)


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
    async def _pull() -> None:
        redis = get_redis()
        try:
            last_run_raw = await redis.get(_COHORTS_LAST_RUN_KEY)
        except Exception:
            logger.exception("Failed to read %s from Redis", _COHORTS_LAST_RUN_KEY)
            last_run_raw = None

        since: datetime | None = None
        if last_run_raw:
            try:
                since = datetime.fromisoformat(last_run_raw) - _COHORTS_OVERLAP
            except ValueError:
                logger.warning(
                    "Invalid %s value in Redis: %r; falling back to full pull",
                    _COHORTS_LAST_RUN_KEY,
                    last_run_raw,
                )
                since = None

        # Capture start timestamp before the fetch so the next window covers
        # anything edited while this task is running.
        run_started_at = datetime.now(timezone.utc)
        started = time.perf_counter()

        async with sync_service_scope() as sync:
            if sync is None:
                return
            async with celery_db():
                synced = await sync.backup_pull_cohorts(
                    suppress_emit=suppress_emit, since=since
                )

        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "notion.backup_pull_cohorts finished: synced=%d duration_ms=%d since=%s",
            synced,
            duration_ms,
            since.isoformat() if since else None,
        )

        try:
            await redis.set(_COHORTS_LAST_RUN_KEY, run_started_at.isoformat())
        except Exception:
            logger.exception("Failed to write %s to Redis", _COHORTS_LAST_RUN_KEY)

    try:
        run_async(_pull())
    except NotionDatabaseUnavailableError as exc:
        logger.warning("backup_pull_cohorts skipped: %s", exc)
