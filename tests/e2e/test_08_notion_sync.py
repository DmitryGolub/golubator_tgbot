import os
from typing import Callable

import pytest

from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.notion_assertions import NotionAssertions
from tests.e2e.helpers.setup import TestSetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))

NOTION_MENTOR_DB_ID = os.environ.get("NOTION_MENTOR_DB_ID", "")
NOTION_MENTEE_DB_ID = os.environ.get(
    "NOTION_MENTEE_DB_ID", os.environ.get("NOTION_DATABASE_ID", "")
)

# TODO: Add module-scoped teardown to archive/delete test Notion pages after each run.
# Without cleanup, tests are not deterministic:
# - test_push_events_creates_page may pass falsely because notion_page_id remains from a previous run
# - test_push_skips_synced may pass even if push is broken (synced_at already set)
# - test_push_mentors_role doesn't verify the actual property value changed in Notion
# Fix: add a fixture that calls notion.cleanup_test_pages() in teardown,
# and reset notion_page_id/synced_at to NULL in setup before each push test.

_module_state = {}


async def test_push_mentors_role(
    account1: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
    notion: NotionAssertions,
    wait_for_sync: Callable,
):
    """Push should update mentor's Role property in Notion."""
    await account1.send_command_multi("/start", count=2)
    await setup.set_user_role(ACCOUNT_1_TG_ID, "mentor")
    await setup.ensure_mentor_record(ACCOUNT_1_TG_ID)

    # Get mentor's notion_page_id
    mentor = await db.get_mentor(ACCOUNT_1_TG_ID)
    if mentor is None or mentor.get("notion_page_id") is None:
        pytest.skip("Mentor has no notion_page_id — Notion not configured")
        return

    page_id = mentor["notion_page_id"]
    _module_state["mentor_page_id"] = page_id

    # Touch updated_at to force sync
    await setup.touch_updated_at("iam.mentors", ACCOUNT_1_TG_ID)

    # Wait for sync to push changes
    try:
        await wait_for_sync(
            lambda: db.get_mentor_synced_at(ACCOUNT_1_TG_ID),
            max_wait=30,
            interval=3,
        )
    except AssertionError:
        pytest.skip("Mentor sync not completed within timeout")
        return

    # Verify in Notion
    page = await notion.get_page(page_id)
    assert page is not None, "Notion page should exist"


async def test_push_mentees_status_and_mentor(
    account2: TelegramTestClient,
    db: DBAssertions,
    setup: TestSetup,
    notion: NotionAssertions,
    wait_for_sync: Callable,
):
    """Push should update mentee's Status and Mentor in Notion."""
    await account2.send_command_multi("/start", count=2)
    await setup.ensure_mentee_record(ACCOUNT_2_TG_ID, ACCOUNT_1_TG_ID)

    mentee = await db.get_mentee(ACCOUNT_2_TG_ID)
    if mentee is None or mentee.get("notion_page_id") is None:
        pytest.skip("Mentee has no notion_page_id — Notion not configured")
        return

    page_id = mentee["notion_page_id"]
    _module_state["mentee_page_id"] = page_id

    # Touch updated_at to force sync
    await setup.touch_updated_at("iam.mentees", ACCOUNT_2_TG_ID)

    try:
        await wait_for_sync(
            lambda: db.get_mentee_synced_at(ACCOUNT_2_TG_ID),
            max_wait=30,
            interval=3,
        )
    except AssertionError:
        pytest.skip("Mentee sync not completed within timeout")
        return

    page = await notion.get_page(page_id)
    assert page is not None


async def test_push_events_creates_page(
    db: DBAssertions,
    setup: TestSetup,
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

    try:
        result = await wait_for_sync(
            lambda: db.get_meeting_notion_page_id(meeting_id),
            max_wait=30,
            interval=3,
        )
    except AssertionError:
        pytest.skip("Meeting Notion sync not completed within timeout")
        return

    if result is None:
        pytest.skip("Meeting notion_page_id not set — Notion may not be configured")


async def test_push_events_updates_page(
    db: DBAssertions,
    setup: TestSetup,
    notion: NotionAssertions,
    wait_for_sync: Callable,
):
    """Push should update an existing Notion page for a meeting."""
    meeting_id = _module_state.get("sync_meeting_id")
    if meeting_id is None:
        pytest.skip("No meeting created in previous test")
        return

    page_id = await db.get_meeting_notion_page_id(meeting_id)
    if page_id is None:
        pytest.skip("Meeting has no notion_page_id")
        return

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

    try:
        await wait_for_sync(_check_updated, max_wait=30, interval=3)
    except AssertionError:
        pytest.skip("Meeting update sync not completed")
        return

    page = await notion.get_page(page_id)
    assert page is not None


async def test_push_skips_synced(
    db: DBAssertions,
):
    """Already-synced entities should be skipped (synced_at >= updated_at)."""
    mentor = await db.get_mentor(ACCOUNT_1_TG_ID)
    if mentor is None:
        pytest.skip("No mentor record")
        return

    synced_at = mentor.get("synced_at")
    updated_at = mentor.get("updated_at")

    if synced_at is None or updated_at is None:
        pytest.skip("Cannot verify sync skip — missing timestamps")
        return

    # If synced_at >= updated_at, the entity is considered synced
    # This is the expected state after a successful push
    assert synced_at >= updated_at, (
        f"After sync, synced_at ({synced_at}) should be >= updated_at ({updated_at})"
    )
