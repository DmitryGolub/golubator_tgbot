import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InaccessibleMessage, Message

logger = logging.getLogger(__name__)


async def safe_edit_text(callback: CallbackQuery, text: str, **kwargs) -> None:
    """Edit callback message, handling inaccessible and unmodified messages."""
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer(text[:200])
        return
    try:
        await callback.message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def safe_msg(callback: CallbackQuery) -> Message:
    """Extract Message from callback, raising TypeError if inaccessible."""
    msg = callback.message
    if not isinstance(msg, Message):
        raise TypeError("Message is inaccessible")
    return msg


def split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split long text into chunks suitable for Telegram messages."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks
