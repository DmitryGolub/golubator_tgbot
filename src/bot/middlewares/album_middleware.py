import asyncio
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

_ALBUM_COLLECT_DELAY = 0.6
_RECENT_TTL = 60.0
_RECENT_MAX = 1000


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
        self._recent_groups: OrderedDict[str, float] = OrderedDict()
        self._lock = asyncio.Lock()

    def _is_recent(self, group_id: str) -> bool:
        now = time.monotonic()
        ts = self._recent_groups.get(group_id)
        if ts is not None and now - ts < _RECENT_TTL:
            return True
        if ts is not None:
            self._recent_groups.pop(group_id, None)
        return False

    def _remember_group(self, group_id: str) -> None:
        now = time.monotonic()
        self._recent_groups[group_id] = now
        self._recent_groups.move_to_end(group_id)
        while len(self._recent_groups) > _RECENT_MAX:
            self._recent_groups.popitem(last=False)
        # Opportunistic cleanup of stale entries
        cutoff = now - _RECENT_TTL
        stale = [k for k, v in self._recent_groups.items() if v < cutoff]
        for k in stale:
            self._recent_groups.pop(k, None)

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
            if self._is_recent(group_id):
                # Album already flushed to handler; ignore late item.
                return None
            existing = self._groups.get(group_id)
            if existing is not None:
                existing.append(event)
                return None
            messages: list[Message] = [event]
            self._groups[group_id] = messages

        await asyncio.sleep(_ALBUM_COLLECT_DELAY)

        async with self._lock:
            album = self._groups.pop(group_id, messages)
            self._remember_group(group_id)

        data["album"] = album
        return await handler(event, data)
