import logging
import threading
import time

from celery.signals import (
    heartbeat_sent,
    task_postrun,
    task_prerun,
    worker_process_init,
    worker_ready,
)

logger = logging.getLogger(__name__)

# Liveness threshold: if no heartbeat update for this many seconds, worker is
# considered unhealthy. The daemon thread ticks every 5s, and Celery signals
# fire on any activity, so 30s catches a genuinely frozen process/GIL while
# tolerating brief GIL contention from long-running solo-pool tasks.
MAX_STALE_SECONDS = 30.0
_TICK_INTERVAL_SECONDS = 5.0

_last_heartbeat: float = time.monotonic()
_lock = threading.Lock()
_started = False


def touch() -> None:
    global _last_heartbeat
    with _lock:
        _last_heartbeat = time.monotonic()


def _age() -> float:
    with _lock:
        return time.monotonic() - _last_heartbeat


def is_alive(max_stale: float = MAX_STALE_SECONDS) -> bool:
    age = _age()
    if age > max_stale:
        logger.warning(
            "Celery worker healthcheck: heartbeat stale (%.1fs > %.1fs)",
            age,
            max_stale,
        )
        return False
    return True


def _tick_loop() -> None:
    while True:
        time.sleep(_TICK_INTERVAL_SECONDS)
        touch()


def _on_signal(*args, **kwargs) -> None:
    touch()


def start_worker_heartbeat() -> None:
    """Start in-memory heartbeat: daemon tick thread + Celery signal hooks.

    Tick thread confirms the process/GIL can run Python code even while the
    solo pool is executing a long task. Signals additionally refresh the
    heartbeat whenever the worker observes activity.
    """
    global _started
    if _started:
        return
    _started = True

    touch()

    worker_ready.connect(_on_signal, weak=False)
    worker_process_init.connect(_on_signal, weak=False)
    task_prerun.connect(_on_signal, weak=False)
    task_postrun.connect(_on_signal, weak=False)
    heartbeat_sent.connect(_on_signal, weak=False)

    thread = threading.Thread(
        target=_tick_loop, name="celery-worker-heartbeat", daemon=True
    )
    thread.start()
