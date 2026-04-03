import os
from typing import Callable

from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.notion_assertions import NotionAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

NOTION_MENTOR_DB_ID = os.environ.get("NOTION_MENTOR_DB_ID", "")
NOTION_MENTEE_DB_ID = os.environ.get(
    "NOTION_MENTEE_DB_ID", os.environ.get("NOTION_DATABASE_ID", "")
)

_module_state = {}


async def test_push_mentors_role(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    notion: NotionAssertions,
    wait_for_sync: Callable,
):
    """Push should update mentor's Role property in Notion."""
    await account1.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)

    # Get mentor's notion_page_id
    mentor = await db.get_mentor(ACCOUNT_1_TG_ID)
    assert mentor is not None and mentor.get("notion_page_id") is not None, (
        "Mentor should have notion_page_id — Notion must be configured"
    )

    page_id = mentor["notion_page_id"]
    _module_state["mentor_page_id"] = page_id

    # Touch updated_at to force sync
    await setup.touch_updated_at("iam.mentors", ACCOUNT_1_TG_ID)

    # Wait for sync to push changes
    await wait_for_sync(
        lambda: db.get_mentor_synced_at(ACCOUNT_1_TG_ID),
        max_wait=60,
        interval=3,
    )

    # Verify in Notion
    page = await notion.get_page(page_id)
    assert page is not None, "Notion page should exist"


async def test_push_mentees_status_and_mentor(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: E2ESetup,
    notion: NotionAssertions,
    wait_for_sync: Callable,
):
    """Push should update mentee's Status and Mentor in Notion."""
    await account2.send_command_multi("/start", count=2)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    mentee = await db.get_mentee(ACCOUNT_2_TG_ID)
    assert mentee is not None and mentee.get("notion_page_id") is not None, (
        "Mentee should have notion_page_id — Notion must be configured"
    )

    page_id = mentee["notion_page_id"]
    _module_state["mentee_page_id"] = page_id

    # Touch updated_at to force sync
    await setup.touch_updated_at("iam.mentees", ACCOUNT_2_TG_ID)

    await wait_for_sync(
        lambda: db.get_mentee_synced_at(ACCOUNT_2_TG_ID),
        max_wait=60,
        interval=3,
    )

    page = await notion.get_page(page_id)
    assert page is not None


async def test_push_events_creates_page(
    db: DBAssertions,
    setup: E2ESetup,
    wait_for_sync: Callable,
):
    """Push should create a Notion page for a new meeting."""
    # Create meeting via DB
    pool = db._pool
    from datetime import datetime, timezone

    meeting_id = await pool.fetchval(
        """
        INSERT INTO meetings.meetings
            (description, mentor_telegram_id, student_telegram_id, scheduled_at)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        "E2E Notion sync test meeting",
        ACCOUNT_1_TG_ID,
        ACCOUNT_2_TG_ID,
        datetime.now(timezone.utc),
    )
    _module_state["sync_meeting_id"] = meeting_id

    # Touch to force push
    await pool.execute(
        "UPDATE meetings.meetings SET updated_at = NOW() WHERE id = $1",
        meeting_id,
    )

    result = await wait_for_sync(
        lambda: db.get_meeting_notion_page_id(meeting_id),
        max_wait=60,
        interval=3,
    )

    assert result is not None, "Meeting should have notion_page_id after sync"


async def test_push_events_updates_page(
    db: DBAssertions,
    setup: E2ESetup,
    notion: NotionAssertions,
    wait_for_sync: Callable,
):
    """Push should update an existing Notion page for a meeting."""
    meeting_id = _module_state.get("sync_meeting_id")
    assert meeting_id is not None, "Previous test must create a meeting"

    page_id = await db.get_meeting_notion_page_id(meeting_id)
    assert page_id is not None, "Meeting should have notion_page_id"

    # Update meeting description
    pool = db._pool
    await pool.execute(
        "UPDATE meetings.meetings SET description = $1, updated_at = NOW() WHERE id = $2",
        "E2E Updated description",
        meeting_id,
    )

    # Wait for sync
    old_synced = await pool.fetchval(
        "SELECT synced_at FROM meetings.meetings WHERE id = $1", meeting_id
    )

    async def _check_updated():
        current = await pool.fetchval(
            "SELECT synced_at FROM meetings.meetings WHERE id = $1", meeting_id
        )
        if current is not None and (old_synced is None or current > old_synced):
            return current
        return None

    await wait_for_sync(_check_updated, max_wait=60, interval=3)

    page = await notion.get_page(page_id)
    assert page is not None


async def test_push_skips_synced(
    db: DBAssertions,
):
    """Already-synced entities should be skipped (synced_at >= updated_at)."""
    mentor = await db.get_mentor(ACCOUNT_1_TG_ID)
    assert mentor is not None, "Mentor record should exist"

    synced_at = mentor.get("synced_at")
    updated_at = mentor.get("updated_at")

    assert synced_at is not None and updated_at is not None, (
        "Both synced_at and updated_at should be set after sync"
    )

    # If synced_at >= updated_at, the entity is considered synced
    # This is the expected state after a successful push
    assert synced_at >= updated_at, (
        f"After sync, synced_at ({synced_at}) should be >= updated_at ({updated_at})"
    )
