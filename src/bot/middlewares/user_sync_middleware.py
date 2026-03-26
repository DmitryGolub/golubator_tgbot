from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.dao.user import UserDAO


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
                await self._sync_user(tg_user)

        return await handler(event, data)

    @staticmethod
    async def _sync_user(tg_user) -> None:
        existing = await UserDAO.find_one_or_none(telegram_id=tg_user.id)
        if not existing:
            return

        updates = {}
        if existing.registered_at is None:
            updates["registered_at"] = datetime.now(timezone.utc)
        if existing.username != tg_user.username:
            updates["username"] = tg_user.username

        if updates:
            await UserDAO.update(telegram_id=tg_user.id, **updates)
