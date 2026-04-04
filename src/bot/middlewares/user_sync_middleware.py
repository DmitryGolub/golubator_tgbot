import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.services.auth import AuthService

logger = logging.getLogger(__name__)

_SYNC_INTERVAL = 60
_last_sync: dict[int, float] = {}


class UserSyncMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            inner = event.event
            tg_user = getattr(inner, "from_user", None)
            if tg_user:
                now = time.monotonic()
                if now - _last_sync.get(tg_user.id, 0) >= _SYNC_INTERVAL:
                    try:
                        await AuthService.ensure_user(tg_user)
                        _last_sync[tg_user.id] = now
                    except Exception:
                        logger.warning(
                            "UserSync failed for %s", tg_user.id, exc_info=True
                        )

        return await handler(event, data)
