from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message


def safe_message(callback: CallbackQuery) -> Message:
    """Extract Message from callback, raising TypeError if inaccessible."""
    msg = callback.message
    if not isinstance(msg, Message):
        raise TypeError("Message is inaccessible")
    return msg


async def safe_edit_text(
    callback: CallbackQuery, text: str, **kwargs
) -> Message | None:
    """Edit callback message text, falling back to alert if message is inaccessible."""
    msg = callback.message
    if not isinstance(msg, Message):
        await callback.answer(text[:200], show_alert=True)
        return None
    try:
        return await msg.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
        return None
