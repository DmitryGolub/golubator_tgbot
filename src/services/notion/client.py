from __future__ import annotations

import asyncio
import logging
import time

import httpx
from notion_client import AsyncClient
from notion_client.errors import APIResponseError

# Cut off hung Notion calls well before task_soft_time_limit (180s) kicks in.
_NOTION_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)

logger = logging.getLogger(__name__)

# Max 3 requests per second for Notion API
_RATE_LIMIT = 3
_RATE_PERIOD = 1.0


class _RateLimiter:
    """Token-bucket rate limiter shared across all repos using the same token.

    Asyncio primitives (Lock) are bound to a specific event loop. The worker
    runs on a single persistent loop, so primitives get created once on first
    use; the loop-id guard still recreates them if the limiter is reused from
    a different loop (e.g. in the bot process).
    """

    def __init__(self, rate: int = _RATE_LIMIT, period: float = _RATE_PERIOD):
        self._rate = rate
        self._period = period
        self._timestamps: list[float] = []
        self._lock: asyncio.Lock | None = None
        self._loop_id: int | None = None

    def _ensure_primitives(self) -> None:
        current_loop_id = id(asyncio.get_running_loop())
        if self._loop_id != current_loop_id:
            self._lock = asyncio.Lock()
            self._timestamps = []
            self._loop_id = current_loop_id

    async def acquire(self) -> None:
        self._ensure_primitives()
        while True:
            async with self._lock:
                now = time.monotonic()
                self._timestamps = [
                    t for t in self._timestamps if now - t < self._period
                ]
                if len(self._timestamps) < self._rate:
                    self._timestamps.append(time.monotonic())
                    return
                sleep_time = self._period - (now - self._timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)


# Global rate limiter per token (single integration = single rate limit)
_rate_limiters: dict[str, _RateLimiter] = {}


def _get_rate_limiter(token: str) -> _RateLimiter:
    if token not in _rate_limiters:
        _rate_limiters[token] = _RateLimiter()
    return _rate_limiters[token]


class NotionDatabaseUnavailableError(Exception):
    """Raised when a Notion database is not accessible."""


class NotionPageArchivedError(Exception):
    """Raised when attempting to edit an archived Notion page."""


def _is_archived_error(exc: APIResponseError) -> bool:
    return "archived" in str(exc).lower()


class NotionClient:
    """Base async client for Notion API with rate limiting.

    Each repo wraps this client with a specific database_id.
    """

    def __init__(self, token: str, database_id: str):
        self._token = token
        self._client: AsyncClient | None = None
        self._client_loop_id: int | None = None
        self._database_id = database_id
        self._data_source_id: str | None = None
        self._rate_limiter = _get_rate_limiter(token)
        self._users_cache: dict[str, str] | None = None

    async def _ensure_client(self) -> AsyncClient:
        """Create the AsyncClient lazily and recreate it if the event loop
        ever changes underneath us.

        Normally the worker holds a single long-lived loop (see
        src/tasks/_db.py) and this branch runs exactly once per process. The
        loop-id guard remains as a defensive measure for any caller that
        happens to invoke the client from a different loop.
        """
        current_loop_id = id(asyncio.get_running_loop())
        if self._client_loop_id != current_loop_id:
            old = self._client
            if old is not None:
                try:
                    await old.aclose()
                except Exception:
                    logger.warning("Failed to close stale Notion client", exc_info=True)
            self._client = AsyncClient(auth=self._token)
            # notion_client's setter copies options.timeout_ms onto the httpx
            # client; override it afterwards so a hung remote can't pin the
            # worker for the SDK default (60s).
            self._client.client.timeout = _NOTION_HTTP_TIMEOUT
            self._client_loop_id = current_loop_id
            self._data_source_id = None
        return self._client

    @property
    def database_id(self) -> str:
        return self._database_id

    async def _resolve_data_source_id(self) -> str:
        if self._data_source_id is None:
            await self._rate_limiter.acquire()
            try:
                client = await self._ensure_client()
                db = await client.databases.retrieve(database_id=self._database_id)
            except APIResponseError as e:
                logger.warning(
                    "Notion database %s unavailable: %s",
                    self._database_id,
                    str(e),
                )
                raise NotionDatabaseUnavailableError(
                    f"Database {self._database_id} is not accessible"
                ) from e
            sources = db.get("data_sources", [])
            if not sources:
                raise RuntimeError(
                    f"No data sources found for database {self._database_id}"
                )
            self._data_source_id = sources[0]["id"]
        return self._data_source_id

    @property
    def data_source_id(self) -> str | None:
        return self._data_source_id

    async def query_pages(
        self,
        *,
        filter: dict | None = None,
        page_size: int = 100,
        start_cursor: str | None = None,
    ) -> dict:
        ds_id = await self._resolve_data_source_id()
        await self._rate_limiter.acquire()
        kwargs: dict = {"data_source_id": ds_id, "page_size": page_size}
        if filter:
            kwargs["filter"] = filter
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        client = await self._ensure_client()
        return await client.data_sources.query(**kwargs)

    async def get_all_pages(self, filter: dict | None = None) -> list[dict]:
        pages: list[dict] = []
        cursor: str | None = None
        while True:
            resp = await self.query_pages(
                filter=filter, page_size=100, start_cursor=cursor
            )
            pages.extend(resp["results"])
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return pages

    async def get_page(self, page_id: str) -> dict | None:
        try:
            await self._rate_limiter.acquire()
            client = await self._ensure_client()
            return await client.pages.retrieve(page_id=page_id)
        except APIResponseError as e:
            logger.error("Notion get_page %s failed: %s", page_id, e)
            return None

    async def get_block_children(self, block_id: str) -> list[dict]:
        blocks: list[dict] = []
        try:
            cursor: str | None = None
            while True:
                await self._rate_limiter.acquire()
                client = await self._ensure_client()
                resp = await client.blocks.children.list(
                    block_id=block_id, start_cursor=cursor, page_size=100
                )
                blocks.extend(resp.get("results", []))
                if not resp.get("has_more"):
                    break
                cursor = resp.get("next_cursor")
        except APIResponseError as e:
            logger.error("Notion get_block_children %s failed: %s", block_id, e)
        return blocks

    async def create_page(
        self,
        properties: dict,
        *,
        children: list[dict] | None = None,
    ) -> dict | None:
        try:
            ds_id = await self._resolve_data_source_id()
            await self._rate_limiter.acquire()
            kwargs: dict = {
                "parent": {"data_source_id": ds_id},
                "properties": properties,
            }
            if children:
                kwargs["children"] = children
            client = await self._ensure_client()
            return await client.pages.create(**kwargs)
        except APIResponseError as e:
            logger.error("Notion create_page failed: %s", e)
            return None

    async def update_page(self, page_id: str, properties: dict) -> dict | None:
        try:
            await self._rate_limiter.acquire()
            client = await self._ensure_client()
            return await client.pages.update(page_id=page_id, properties=properties)
        except APIResponseError as e:
            if _is_archived_error(e):
                logger.info("Notion page %s is archived; skipping update", page_id)
                raise NotionPageArchivedError(page_id) from e
            logger.error("Notion update_page %s failed: %s", page_id, e)
            return None

    async def archive_page(self, page_id: str) -> bool:
        try:
            await self._rate_limiter.acquire()
            client = await self._ensure_client()
            await client.pages.update(page_id=page_id, archived=True)
            return True
        except APIResponseError as e:
            logger.error("Notion archive_page %s failed: %s", page_id, e)
            return False

    async def get_schema(self) -> dict:
        try:
            ds_id = await self._resolve_data_source_id()
            await self._rate_limiter.acquire()
            client = await self._ensure_client()
            db = await client.data_sources.retrieve(data_source_id=ds_id)
            return db.get("properties", {})
        except APIResponseError as e:
            logger.error("Notion get_schema failed: %s", e)
            return {}

    async def update_schema(self, properties: dict) -> bool:
        try:
            ds_id = await self._resolve_data_source_id()
            await self._rate_limiter.acquire()
            client = await self._ensure_client()
            await client.data_sources.update(
                data_source_id=ds_id, properties=properties
            )
            return True
        except APIResponseError as e:
            logger.error("Notion update_schema failed: %s", e)
            return False

    async def get_users(self) -> dict[str, str]:
        """Return mapping {email: notion_user_id} for workspace users. Cached."""
        if self._users_cache is not None:
            return self._users_cache

        result: dict[str, str] = {}
        try:
            await self._rate_limiter.acquire()
            client = await self._ensure_client()
            resp = await client.users.list()
            for user in resp.get("results", []):
                email = (user.get("person") or {}).get("email")
                if email:
                    result[email.lower()] = user["id"]
        except APIResponseError as e:
            logger.error("Notion get_users failed: %s", e)

        self._users_cache = result
        return result

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
