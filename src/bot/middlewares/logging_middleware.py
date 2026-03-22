import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.core.logging_config import ctx_telegram_id

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        user_id = None
        update_type = event.event_type

        inner = event.event
        if hasattr(inner, "from_user") and inner.from_user:
            user_id = inner.from_user.id

        # Extract action description
        if update_type == "message" and hasattr(inner, "text") and inner.text:
            action = inner.text.split()[0] if inner.text.startswith("/") else "text"
        elif update_type == "callback_query" and hasattr(inner, "data"):
            action = inner.data or ""
        elif update_type == "message":
            action = getattr(inner, "content_type", "")
        else:
            action = update_type

        token = ctx_telegram_id.set(user_id)
        start = time.perf_counter()
        try:
            result = await handler(event, data)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                "Update %s: %s user=%s [%.0fms]",
                event.update_id,
                action,
                user_id,
                elapsed,
            )
            return result
        except Exception as exc:
            logger.error(
                "Update %s FAILED: %s user=%s error=%s",
                event.update_id,
                action,
                user_id,
                exc,
            )
            raise
        finally:
            ctx_telegram_id.reset(token)
