import logging
import sys
from contextvars import ContextVar

ctx_telegram_id: ContextVar[int | None] = ContextVar("telegram_id", default=None)

_configured = False


class _ContextFilter(logging.Filter):
    """Inject contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.telegram_id = ctx_telegram_id.get()  # type: ignore[attr-defined]
        return True


_DEV_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | tg=%(telegram_id)s | %(message)s"
)


def setup_logging(level: str = "INFO", fmt: str = "dev") -> None:
    """Configure root logger. Call once at startup."""
    global _configured  # noqa: PLW0603
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())

    if fmt == "json":
        from pythonjsonlogger.json import JsonFormatter

        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(telegram_id)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    else:
        formatter = logging.Formatter(_DEV_FORMAT)

    handler.setFormatter(formatter)
    root.addHandler(handler)

    for noisy in (
        "aiogram.event",
        "httpx",
        "httpcore",
        "asyncio",
        "celery.beat",
        "celery.worker.strategy",
        "celery.app.trace",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
