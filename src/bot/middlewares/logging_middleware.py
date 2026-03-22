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
        chat_id = None
        update_type = event.event_type

        inner = event.event
        if hasattr(inner, "from_user") and inner.from_user:
            user_id = inner.from_user.id
        if hasattr(inner, "chat") and inner.chat:
            chat_id = inner.chat.id

        token = ctx_telegram_id.set(user_id)
        start = time.perf_counter()
        try:
            logger.info(
                "Update %s: type=%s user=%s chat=%s",
                event.update_id,
                update_type,
                user_id,
                chat_id,
            )
            result = await handler(event, data)
            elapsed = (time.perf_counter() - start) * 1000
            logger.debug("Update %s handled in %.1fms", event.update_id, elapsed)
            return result
        except Exception:
            logger.exception(
                "Update %s failed: type=%s user=%s",
                event.update_id,
                update_type,
                user_id,
            )
            raise
        finally:
            ctx_telegram_id.reset(token)
