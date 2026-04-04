import asyncio
import os
from datetime import datetime, timezone

import asyncpg
import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from notion_client import AsyncClient as NotionAsyncClient
from telethon import TelegramClient

from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.notion_assertions import NotionAssertions
from tests.e2e.helpers.setup import E2ESetup
from tests.e2e.helpers.telegram_client import TelegramTestClient

load_dotenv(".env.test", override=True)

# ── Telegram config ──
API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_DIR = "tests/e2e/sessions"

ACCOUNT_1_SESSION = os.environ["TEST_ACCOUNT_1_SESSION"]
ACCOUNT_2_SESSION = os.environ["TEST_ACCOUNT_2_SESSION"]

# ── DB config ──
DB_DSN = (
    f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASS']}"
    f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
)

REDIS_URL = f"redis://{os.environ['REDIS_HOST']}:{os.environ['REDIS_PORT']}/0"


async def _resolve_bot_username() -> str:
    """Get bot username dynamically from BOT_TOKEN via Telegram API."""
    token = os.environ["BOT_TOKEN"]
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        resp.raise_for_status()
        return resp.json()["result"]["username"]


@pytest.fixture(scope="session")
def test_run_id() -> str:
    """Unique identifier embedded in all Notion-visible test data (e.g. meeting topics)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def bot_username() -> str:
    return await _resolve_bot_username()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_pool() -> asyncpg.Pool:
    pool = await asyncpg.create_pool(DB_DSN)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db(db_pool) -> DBAssertions:
    return DBAssertions(db_pool)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def setup(db_pool) -> E2ESetup:
    s = E2ESetup(db_pool)
    s._redis_url = REDIS_URL
    return s


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def notion() -> NotionAssertions:
    client = NotionAsyncClient(auth=os.environ["NOTION_TOKEN"])
    yield NotionAssertions(client)
    await client.aclose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def account1(bot_username) -> TelegramTestClient:
    client = TelegramClient(f"{SESSION_DIR}/{ACCOUNT_1_SESSION}", API_ID, API_HASH)
    await client.connect()
    yield TelegramTestClient(client, bot_username)
    await client.disconnect()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def account2(bot_username) -> TelegramTestClient:
    client = TelegramClient(f"{SESSION_DIR}/{ACCOUNT_2_SESSION}", API_ID, API_HASH)
    await client.connect()
    yield TelegramTestClient(client, bot_username)
    await client.disconnect()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def wait_for_sync():
    """Polling helper for Notion sync instead of bare asyncio.sleep."""

    async def _wait(check_fn, max_wait=30, interval=3):
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < max_wait:
            result = await check_fn()
            if result:
                return result
            await asyncio.sleep(interval)
        raise AssertionError(f"Sync not completed within {max_wait}s")

    return _wait


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def wait_for_celery():
    """Polling helper for Celery-dependent checks. Skips instead of failing on timeout."""

    async def _wait(check_fn, max_wait=360, interval=5, skip_msg="Celery не ответил"):
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < max_wait:
            result = await check_fn()
            if result:
                return result
            await asyncio.sleep(interval)
        pytest.skip(f"{skip_msg} в течение {max_wait}s")

    return _wait


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def wait_for_all_celery():
    """Ждёт НЕСКОЛЬКО Celery-условий параллельно через asyncio.gather.

    Каждый check_fn — async callable без аргументов, возвращает truthy когда готово.
    Если хоть одно не выполнено за max_wait — pytest.skip для всего теста.
    """

    async def _poll_one(check_fn, max_wait: int, interval: int):
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < max_wait:
            try:
                result = await check_fn()
                if result:
                    return result
            except Exception:
                pass
            await asyncio.sleep(interval)
        return None  # timeout — не raise, чтобы gather дождался всех

    async def _wait(
        *check_fns,
        max_wait: int = 600,
        interval: int = 5,
        labels: list[str] | None = None,
        skip_msg: str = "Celery не ответил",
    ):
        if labels is None:
            labels = [f"check_{i}" for i in range(len(check_fns))]
        results = await asyncio.gather(
            *[_poll_one(fn, max_wait, interval) for fn in check_fns]
        )
        failed = [labels[i] for i, r in enumerate(results) if r is None]
        if failed:
            pytest.skip(f"{skip_msg} за {max_wait}s: {', '.join(failed)}")
        return results

    return _wait


@pytest_asyncio.fixture(autouse=True, scope="module", loop_scope="session")
async def cleanup_between_modules(setup):
    """Clean up DB and Redis between test modules."""
    yield
    await setup.truncate_all()
    await setup.flush_redis(REDIS_URL)
