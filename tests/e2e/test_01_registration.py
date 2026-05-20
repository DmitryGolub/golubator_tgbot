import os
from typing import Callable

from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.telegram_client import TelegramTestClient

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))
ACCOUNT_2_TG_ID = int(os.environ.get("TEST_ACCOUNT_2_TG_ID", "0"))


async def test_start_command_registers_user(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """
    /start -> bot responds with a welcome message -> User is saved in DB.
    All actions via bot, DB is read-only for assertions.
    """
    # 1. Send /start via MTProto
    responses = await account1.send_command_multi("/start", count=2)

    # 2. Check bot response
    assert len(responses) >= 1, "Bot did not respond to /start"
    welcome = responses[0]
    assert welcome.text is not None
    assert len(welcome.text) > 0

    # 3. If user has permissions — second message is the menu
    if len(responses) >= 2:
        menu_msg = responses[1]
        assert menu_msg.reply_markup is not None, "Menu should have inline keyboard"

    # 4. Read-only DB assertion
    user = await db.assert_user_exists(ACCOUNT_1_TG_ID)
    assert user["telegram_id"] == ACCOUNT_1_TG_ID


async def test_start_account2(
    account2: TelegramTestClient,
    db: DBAssertions,
):
    """
    /start with the second account -> bot responds -> User is saved in DB.
    """
    # 1. Send /start via MTProto
    responses = await account2.send_command_multi("/start", count=2)

    # 2. Check bot response
    assert len(responses) >= 1, "Bot did not respond to /start"
    welcome = responses[0]
    assert welcome.text is not None
    assert len(welcome.text) > 0

    # 3. If user has permissions — second message is the menu
    if len(responses) >= 2:
        menu_msg = responses[1]
        assert menu_msg.reply_markup is not None, "Menu should have inline keyboard"

    # 4. Read-only DB assertion
    user = await db.assert_user_exists(ACCOUNT_2_TG_ID)
    assert user["telegram_id"] == ACCOUNT_2_TG_ID


async def test_notion_link_on_start(
    account1: TelegramTestClient,
    db: DBAssertions,
    wait_for_sync: Callable,
):
    """
    After /start, the bot should link a Notion page to the user in background.
    Poll DB until mentor or mentee record gets a notion_page_id.
    Skip if Notion linking did not happen within the timeout.
    """
    # Ensure user is registered (may already be from previous test)
    await account1.send_command_multi("/start", count=2)

    async def _check_notion_linked():
        mentor = await db.get_mentor(ACCOUNT_1_TG_ID)
        if mentor and mentor.get("notion_page_id"):
            return mentor

        mentee = await db.get_mentee(ACCOUNT_1_TG_ID)
        if mentee and mentee.get("notion_page_id"):
            return mentee

        return None

    record = await wait_for_sync(_check_notion_linked, max_wait=60, interval=3)

    assert record.get("notion_page_id") is not None, (
        "Expected notion_page_id to be set on mentor or mentee record"
    )
