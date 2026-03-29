from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.services.auth import AuthService


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
                await AuthService.ensure_user(tg_user)

        return await handler(event, data)
