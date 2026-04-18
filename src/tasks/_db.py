"""Shared async runtime for Celery worker (-P solo).

A single daemon thread hosts a persistent asyncio event loop. The worker's
`AsyncEngine`, aiogram `Bot` and Notion clients are created once at worker
startup inside that loop and reused by every Celery task. This avoids the
memory creep caused by recreating those heavyweight objects per task.

Public API:
- `run_async(coro)` — called from Celery's main thread, blocks until the
  coroutine completes in the worker loop.
- `celery_db()` — no-op async context manager kept for backwards compatibility
  with existing task code (was previously creating a fresh engine per task).
- `get_worker_bot()` — returns the singleton aiogram Bot bound to the worker
  loop.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from celery.signals import worker_shutdown

from src.core import database
from src.core.config import settings

logger = logging.getLogger(__name__)

# result() timeout must outlast Celery's hard time limit so the main thread
# stays blocked on the coroutine until Celery itself decides to abort the task.
_DEFAULT_RESULT_TIMEOUT = 300.0
_STARTUP_TIMEOUT = 30.0
_SHUTDOWN_TIMEOUT = 30.0


class _WorkerAsyncRuntime:
    """Hosts a single event loop in a daemon thread + cached Bot."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._bot: Optional[Bot] = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._ready.clear()
            start_error: list[BaseException] = []
            thread = threading.Thread(
                target=self._thread_main,
                args=(start_error,),
                name="celery-worker-asyncio",
                daemon=True,
            )
            thread.start()
            if not self._ready.wait(timeout=_STARTUP_TIMEOUT):
                raise RuntimeError(
                    f"Worker async runtime failed to start within {_STARTUP_TIMEOUT}s"
                )
            if start_error:
                raise start_error[0]
            self._thread = thread

    def stop(self) -> None:
        with self._lock:
            loop = self._loop
            thread = self._thread
            if loop is None or thread is None:
                return
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self._cleanup(), loop).result(
                    timeout=_SHUTDOWN_TIMEOUT
                )
                loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=_SHUTDOWN_TIMEOUT)
            self._thread = None
            self._loop = None
            self._bot = None
            self._ready.clear()

    def _thread_main(self, start_error: list[BaseException]) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            try:
                loop.run_until_complete(self._bootstrap())
            except BaseException as exc:  # noqa: BLE001 — propagate to starter
                start_error.append(exc)
                self._ready.set()
                return
            self._ready.set()
            loop.run_forever()
        finally:
            try:
                loop.close()
            except Exception:
                logger.exception("Failed to close worker runtime event loop")

    async def _bootstrap(self) -> None:
        database.init_engine()
        self._bot = Bot(
            settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        logger.info("Worker async runtime started: engine + bot initialized")

    async def _cleanup(self) -> None:
        bot = self._bot
        if bot is not None:
            try:
                await bot.session.close()
            except Exception:
                logger.exception("Failed to close worker Bot session")

        try:
            from src.services.notion_sync_v2 import close_notion_clients

            await close_notion_clients()
        except Exception:
            logger.exception("Failed to close cached Notion clients")

        engine = database._engine
        if engine is not None:
            try:
                await engine.dispose()
            except Exception:
                logger.exception("Failed to dispose DB engine")
            database._engine = None
            database._session_factory = None

        logger.info("Worker async runtime stopped: resources released")

    # ── Submission ─────────────────────────────────────────────────

    def submit(self, coro: Awaitable[Any]) -> Any:
        if not self._ready.is_set():
            self.start()
        loop = self._loop
        assert loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=_DEFAULT_RESULT_TIMEOUT)
        except BaseException:
            # SoftTimeLimitExceeded / KeyboardInterrupt / TimeoutError —
            # cancel the coroutine on the worker loop so it doesn't keep
            # running after the Celery task has already been aborted.
            future.cancel()
            raise

    @property
    def bot(self) -> Bot:
        if not self._ready.is_set():
            self.start()
        bot = self._bot
        assert bot is not None
        return bot


_runtime = _WorkerAsyncRuntime()


def run_async(coro: Awaitable[Any]) -> Any:
    """Execute a coroutine on the shared worker event loop, blocking the caller."""
    return _runtime.submit(coro)


@asynccontextmanager
async def celery_db():
    """Kept for backwards compatibility: the engine is now shared for the
    worker's lifetime and initialized once at startup.
    """
    yield


def get_worker_bot() -> Bot:
    """Return the aiogram Bot owned by the worker runtime."""
    return _runtime.bot


def start_worker_runtime() -> None:
    """Explicit bootstrap hook for celery_worker entrypoint."""
    _runtime.start()


@worker_shutdown.connect
def _on_worker_shutdown(**_: Any) -> None:
    try:
        _runtime.stop()
    except Exception:
        logger.exception("Error during worker runtime shutdown")


# Fallback for non-standard shutdown paths (e.g. SIGKILL won't fire but
# graceful exits without Celery signals still clean up).
atexit.register(lambda: _runtime.stop() if _runtime._thread is not None else None)
