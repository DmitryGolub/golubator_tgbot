from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.core.config import settings
from src.dao.role import RoleDAO
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
        real_id = tg_user.id
        existing = await UserDAO.find_one_or_none(telegram_id=real_id)

        if existing:
            updates = {}
            if existing.registered_at is None:
                updates["registered_at"] = datetime.now(timezone.utc)
            if existing.username != tg_user.username:
                updates["username"] = tg_user.username
            if updates:
                await UserDAO.update(telegram_id=real_id, **updates)
            return

        # User not found — create a real User record
        is_admin = real_id in settings.admin_ids
        role_obj = await RoleDAO.get_by_name("admin" if is_admin else "student")
        await UserDAO.add(
            telegram_id=real_id,
            username=tg_user.username,
            name=tg_user.full_name,
            role_id=role_obj.id if role_obj else None,
            registered_at=datetime.now(timezone.utc),
        )
