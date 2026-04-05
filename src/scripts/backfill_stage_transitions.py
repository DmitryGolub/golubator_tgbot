"""One-time backfill of stage_transitions history from Notion internal API.

Usage:
    uv run python -m src.scripts.backfill_stage_transitions [--dry-run]

Requires NOTION_TOKEN_V2 and NOTION_SPACE_ID in .env (browser cookie token
and workspace ID from Notion DevTools).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.models.stage_transition import StageTransition
from src.services.notion import NotionClient, NotionMenteeRepo

logger = logging.getLogger(__name__)

BACKFILL_SOURCE = "notion_activity_backfill"
BATCH_SIZE = 50


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )


def _make_db() -> tuple:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


def _build_mentee_repo() -> NotionMenteeRepo | None:
    token = settings.NOTION_TOKEN
    mentee_db_id = settings.NOTION_MENTEE_DB_ID or settings.NOTION_DATABASE_ID
    if not token or not mentee_db_id:
        return None
    return NotionMenteeRepo(NotionClient(token, mentee_db_id))


def _extract_prop_value(properties: dict, prop_id: str) -> str | None:
    """Extract a property value from internal API block_data properties.

    Internal API uses short property IDs as keys and [["value"]] format.
    """
    if not properties:
        return None

    raw = properties.get(prop_id)
    if not raw:
        return None

    # Internal format: [["value"]]
    if isinstance(raw, list) and raw and isinstance(raw[0], list) and raw[0]:
        return raw[0][0]

    return None


async def _fetch_activity_log(
    client: httpx.AsyncClient,
    page_id: str,
    starting_after_id: str = "",
    limit: int = 100,
) -> dict:
    """Fetch activity log for a Notion page via internal API."""
    resp = await client.post(
        "/api/v3/getActivityLog",
        json={
            "spaceId": settings.NOTION_SPACE_ID,
            "startingAfterId": starting_after_id,
            "navigableBlock": {"id": page_id},
            "limit": limit,
        },
    )
    if resp.status_code != 200:
        logger.error("getActivityLog failed: %d %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    return resp.json()


async def _fetch_all_activities(
    client: httpx.AsyncClient,
    page_id: str,
) -> list[dict]:
    """Fetch all activity entries for a page, handling pagination."""
    all_activities: list[dict] = []
    starting_after = ""
    retries = 0
    max_retries = 5

    while True:
        try:
            data = await _fetch_activity_log(client, page_id, starting_after)
            retries = 0
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and retries < max_retries:
                retries += 1
                wait = 2**retries
                logger.warning("Rate limited, waiting %ds (retry %d)", wait, retries)
                await asyncio.sleep(wait)
                continue
            raise

        activity_ids = data.get("activityIds", [])
        if not activity_ids:
            break

        record_map = data.get("recordMap", {})
        activity_map = record_map.get("activity", {})

        for aid in activity_ids:
            entry = activity_map.get(aid, {}).get("value")
            if entry:
                all_activities.append(entry)

        # Pagination: use last activity ID as cursor
        if len(activity_ids) < 100:
            break
        starting_after = activity_ids[-1]
        await asyncio.sleep(0.5)

    return all_activities


def _parse_status_transitions(
    activities: list[dict], status_prop_id: str
) -> list[dict]:
    """Parse status changes from activity log entries.

    Returns list of {old_value, new_value, timestamp} sorted by timestamp asc.
    """
    transitions: list[dict] = []

    for activity in activities:
        logger.info(
            "Activity type=%s, edits=%d",
            activity.get("type"),
            len(activity.get("edits", [])),
        )
        edits = activity.get("edits", [])
        for edit in edits:
            block_data = edit.get("block_data")
            if not block_data:
                logger.info("  Edit has no block_data, keys: %s", list(edit.keys()))
                continue

            before_props = (
                block_data.get("before", {})
                .get("block_value", {})
                .get("properties", {})
            )
            after_props = (
                block_data.get("after", {}).get("block_value", {}).get("properties", {})
            )

            old_status = _extract_prop_value(before_props, status_prop_id)
            new_status = _extract_prop_value(after_props, status_prop_id)

            if new_status and old_status != new_status:
                ts_ms = edit.get("timestamp", 0)
                transitions.append(
                    {
                        "old_value": old_status,
                        "new_value": new_status,
                        "timestamp": datetime.fromtimestamp(
                            ts_ms / 1000, tz=timezone.utc
                        ),
                    }
                )

    transitions.sort(key=lambda t: t["timestamp"])
    return transitions


async def _has_backfill_records(session: AsyncSession, user_tid: int) -> bool:
    result = await session.execute(
        select(StageTransition.id)
        .where(
            StageTransition.user_telegram_id == user_tid,
            StageTransition.source == BACKFILL_SOURCE,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _to_uuid(raw: str) -> str:
    """Convert a 32-char hex string to UUID format (8-4-4-4-12)."""
    s = raw.replace("-", "")
    return f"{s[:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"


async def _resolve_collection_id(
    client: httpx.AsyncClient, database_id: str
) -> str | None:
    """Resolve real collection_id from a Notion database block."""
    uuid = _to_uuid(database_id)
    resp = await client.post(
        "/api/v3/getRecordValues",
        json={"requests": [{"id": uuid, "table": "block"}]},
    )
    if resp.status_code != 200:
        logger.error(
            "getRecordValues (block) failed: %d %s", resp.status_code, resp.text[:300]
        )
        return None
    data = resp.json()
    results = data.get("results", [])
    if not results:
        logger.info("_resolve_collection_id: no results for %s", uuid)
        return None
    value = results[0].get("value", {})
    logger.info(
        "_resolve_collection_id: block type=%s, keys=%s",
        value.get("type"),
        list(value.keys())[:15],
    )
    cid = value.get("collection_id")
    if not cid:
        logger.info("_resolve_collection_id: full value=%s", str(value)[:500])
    return cid


async def _fetch_status_prop_id(
    client: httpx.AsyncClient, collection_id: str
) -> str | None:
    """Fetch collection schema to find the property ID for Status."""
    resp = await client.post(
        "/api/v3/getRecordValues",
        json={"requests": [{"id": collection_id, "table": "collection"}]},
    )
    if resp.status_code != 200:
        logger.error("getRecordValues failed: %d %s", resp.status_code, resp.text[:300])
        return None
    data = resp.json()
    results = data.get("results", [])
    if not results:
        return None
    schema = results[0].get("value", {}).get("schema", {})
    for prop_id, prop_def in schema.items():
        if prop_def.get("name") == "Status" and prop_def.get("type") == "status":
            return prop_id
    return None


async def _backfill_user(
    session: AsyncSession,
    client: httpx.AsyncClient,
    page_id: str,
    user_tid: int,
    status_prop_id: str,
    dry_run: bool,
) -> int:
    """Backfill transitions for a single user. Returns number of transitions added."""
    if await _has_backfill_records(session, user_tid):
        logger.info("User %d already has backfill records, skipping", user_tid)
        return 0

    activities = await _fetch_all_activities(client, page_id)
    if not activities:
        logger.info("No activity log for page %s (user %d)", page_id, user_tid)
        return 0

    transitions = _parse_status_transitions(activities, status_prop_id)
    if not transitions:
        logger.info("No status transitions found for user %d", user_tid)
        return 0

    if dry_run:
        logger.info(
            "[DRY RUN] User %d: %d transitions found:", user_tid, len(transitions)
        )
        for t in transitions:
            logger.info(
                "  %s -> %s at %s",
                t["old_value"],
                t["new_value"],
                t["timestamp"].isoformat(),
            )
        return len(transitions)

    # Delete existing initial sync records (None -> X) for this user
    await session.execute(
        delete(StageTransition).where(
            StageTransition.user_telegram_id == user_tid,
            StageTransition.old_value.is_(None),
            StageTransition.source == "notion_sync",
            StageTransition.cohort_type == "Status",
        )
    )

    # Insert full history
    for t in transitions:
        session.add(
            StageTransition(
                user_telegram_id=user_tid,
                cohort_type="Status",
                old_value=t["old_value"],
                new_value=t["new_value"],
                source=BACKFILL_SOURCE,
                created_at=t["timestamp"],
            )
        )

    return len(transitions)


async def main(dry_run: bool = False) -> None:
    _setup_logging()

    if not settings.NOTION_TOKEN_V2:
        logger.error("NOTION_TOKEN_V2 is not set in .env")
        return
    if not settings.NOTION_SPACE_ID:
        logger.error("NOTION_SPACE_ID is not set in .env")
        return

    mentee_repo = _build_mentee_repo()
    if not mentee_repo:
        logger.error("Notion mentee repo not configured (NOTION_TOKEN / DB ID missing)")
        return

    logger.info("Fetching all mentee pages from Notion...")
    mentees = await mentee_repo.get_all()
    logger.info("Found %d mentee pages", len(mentees))

    engine, factory = _make_db()
    try:
        async with httpx.AsyncClient(
            base_url="https://www.notion.so",
            cookies={"token_v2": settings.NOTION_TOKEN_V2},
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        ) as http_client:
            # Resolve real collection_id from Notion database block
            database_id = mentee_repo._client.database_id
            collection_id = await _resolve_collection_id(http_client, database_id)
            if not collection_id:
                logger.error(
                    "Cannot resolve collection_id for database %s", database_id
                )
                return
            status_prop_id = await _fetch_status_prop_id(http_client, collection_id)
            if not status_prop_id:
                logger.error("Could not find Status property in collection schema")
                return
            logger.info("Resolved Status property ID: %s", status_prop_id)

            total = 0
            processed = 0
            skipped = 0

            async with factory() as session:
                from src.models.mentee import Mentee

                for i, mentee_data in enumerate(mentees):
                    try:
                        # Look up mentee in DB by notion_page_id to get telegram_id
                        # (includes placeholder users with negative IDs)
                        result = await session.execute(
                            select(Mentee.telegram_id).where(
                                Mentee.notion_page_id == mentee_data.page_id
                            )
                        )
                        user_tid = result.scalar_one_or_none()
                        if user_tid is None:
                            logger.info(
                                "Mentee page %s not in DB, skipping",
                                mentee_data.page_id,
                            )
                            skipped += 1
                            continue

                        count = await _backfill_user(
                            session,
                            http_client,
                            mentee_data.page_id,
                            user_tid,
                            status_prop_id,
                            dry_run,
                        )
                        total += count
                        processed += 1

                        # Commit in batches
                        if not dry_run and processed % BATCH_SIZE == 0:
                            await session.commit()
                            logger.info(
                                "Committed batch (%d/%d users, %d transitions)",
                                processed,
                                len(mentees),
                                total,
                            )

                        # Rate limit between pages
                        await asyncio.sleep(1)

                    except Exception:
                        logger.exception(
                            "Error processing mentee %s (tg_id=%s)",
                            mentee_data.page_id,
                            user_tid,
                        )

                # Final commit
                if not dry_run:
                    await session.commit()

            logger.info(
                "Done! Processed %d users, %d total transitions %s",
                processed,
                total,
                "(DRY RUN)" if dry_run else "inserted",
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill stage_transitions from Notion activity log"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log transitions without writing to DB",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
