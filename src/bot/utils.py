from aiogram.types import CallbackQuery, Message


def safe_message(callback: CallbackQuery) -> Message:
    """Extract Message from callback, raising TypeError if inaccessible."""
    msg = callback.message
    if not isinstance(msg, Message):
        raise TypeError("Message is inaccessible")
    return msg
