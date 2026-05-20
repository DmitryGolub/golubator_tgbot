"""Unit tests for `src.utils.bot_send.safe_send_message`."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from src.utils.bot_send import safe_send_message


def _recipient(telegram_id=100, registered=True):
    return SimpleNamespace(
        telegram_id=telegram_id,
        registered_at=datetime(2025, 1, 1, tzinfo=timezone.utc) if registered else None,
    )


def _bot_with(send_side_effect=None):
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=send_side_effect)
    return bot


async def test_delivers_to_registered_user():
    bot = _bot_with()
    ok = await safe_send_message(bot, _recipient(), "hi")
    assert ok is True
    bot.send_message.assert_awaited_once()


async def test_skips_placeholder_user():
    bot = _bot_with()
    ok = await safe_send_message(bot, _recipient(telegram_id=-7), "hi")
    assert ok is False
    bot.send_message.assert_not_awaited()


async def test_skips_unregistered_user():
    bot = _bot_with()
    ok = await safe_send_message(bot, _recipient(registered=False), "hi")
    assert ok is False
    bot.send_message.assert_not_awaited()


async def test_swallows_forbidden_error():
    method = SimpleNamespace(__api_method__="sendMessage")
    bot = _bot_with(send_side_effect=TelegramForbiddenError(method=method, message="x"))
    ok = await safe_send_message(bot, _recipient(), "hi")
    assert ok is False


async def test_swallows_chat_not_found():
    method = SimpleNamespace(__api_method__="sendMessage")
    bot = _bot_with(
        send_side_effect=TelegramBadRequest(method=method, message="chat not found")
    )
    ok = await safe_send_message(bot, _recipient(), "hi")
    assert ok is False


async def test_reraises_other_bad_request():
    method = SimpleNamespace(__api_method__="sendMessage")
    bot = _bot_with(
        send_side_effect=TelegramBadRequest(method=method, message="something else")
    )
    with pytest.raises(TelegramBadRequest):
        await safe_send_message(bot, _recipient(), "hi")
