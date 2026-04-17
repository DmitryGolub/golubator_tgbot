import asyncio
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

_ALBUM_COLLECT_DELAY = 0.6


class AlbumMiddleware(BaseMiddleware):
    """Buffers messages belonging to the same Telegram media group.

    aiogram 3 delivers each album item as a separate ``Message`` sharing a
    ``media_group_id``. This middleware waits ``_ALBUM_COLLECT_DELAY`` seconds
    after the first message of a group, then invokes the handler once with the
    full list of messages exposed via ``data["album"]``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._groups: dict[str, list[Message]] = {}
        self._lock = asyncio.Lock()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.media_group_id is None:
            return await handler(event, data)

        group_id = event.media_group_id

        async with self._lock:
            existing = self._groups.get(group_id)
            if existing is not None:
                existing.append(event)
                return None
            messages: list[Message] = [event]
            self._groups[group_id] = messages

        await asyncio.sleep(_ALBUM_COLLECT_DELAY)

        async with self._lock:
            album = self._groups.pop(group_id, messages)

        data["album"] = album
        return await handler(event, data)
