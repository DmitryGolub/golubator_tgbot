from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods.edit_message_text import EditMessageText
from aiogram.types import Message

from src.bot.utils import safe_edit_text


def _make_callback(message=None):
    """Create a mock CallbackQuery with the given message."""
    cb = AsyncMock()
    type(cb).message = PropertyMock(return_value=message)
    return cb


def _make_message():
    """Create a mock Message with async edit_text."""
    msg = MagicMock(spec=Message)
    msg.edit_text = AsyncMock()
    return msg


async def test_edit_text_success():
    msg = _make_message()
    expected = MagicMock(spec=Message)
    msg.edit_text.return_value = expected
    cb = _make_callback(message=msg)

    result = await safe_edit_text(cb, "new text", parse_mode="HTML")

    assert result is expected
    msg.edit_text.assert_awaited_once_with("new text", parse_mode="HTML")


async def test_message_not_modified_returns_none():
    msg = _make_message()
    msg.edit_text.side_effect = TelegramBadRequest(
        method=EditMessageText(chat_id=1, message_id=1, text="x"),
        message="Bad Request: message is not modified",
    )
    cb = _make_callback(message=msg)

    result = await safe_edit_text(cb, "same text")

    assert result is None


async def test_other_bad_request_propagates():
    msg = _make_message()
    msg.edit_text.side_effect = TelegramBadRequest(
        method=EditMessageText(chat_id=1, message_id=1, text="x"),
        message="Bad Request: message can't be edited",
    )
    cb = _make_callback(message=msg)

    with pytest.raises(TelegramBadRequest):
        await safe_edit_text(cb, "text")


async def test_inaccessible_message_falls_back_to_alert():
    cb = _make_callback(message="inaccessible_message_stub")

    result = await safe_edit_text(cb, "alert text here")

    assert result is None
    cb.answer.assert_awaited_once_with("alert text here", show_alert=True)


async def test_inaccessible_message_truncates_long_text():
    cb = _make_callback(message="inaccessible_message_stub")
    long_text = "x" * 300

    await safe_edit_text(cb, long_text)

    cb.answer.assert_awaited_once_with(long_text[:200], show_alert=True)
