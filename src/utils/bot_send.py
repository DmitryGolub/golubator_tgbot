"""Safe wrapper around `Bot.send_message` that skips unreachable recipients.

Covers the two recurring "not really an error" cases:
- the recipient is a placeholder (telegram_id < 0) — no real chat exists;
- the user exists in PG but never ran /start, so `registered_at IS NULL` and
  Telegram refuses with `TelegramForbiddenError`.

Also catches the late-blocking variants (`TelegramForbiddenError`,
`TelegramBadRequest("chat not found")`) so callers don't have to repeat the
same try/except in every send site.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logger = logging.getLogger(__name__)


async def safe_send_message(bot: Bot, recipient: Any, text: str, **kwargs) -> bool:
    """Send `text` to `recipient` (a User-like object with `telegram_id`).

    Returns True when the message was delivered, False when skipped (placeholder,
    unregistered, blocked bot, missing chat). Unexpected errors are re-raised.
    """
    telegram_id = getattr(recipient, "telegram_id", None)
    if telegram_id is None:
        logger.warning("safe_send_message: recipient has no telegram_id, skipping")
        return False

    if telegram_id < 0:
        logger.debug("safe_send_message: placeholder user %s, skipping", telegram_id)
        return False

    if getattr(recipient, "registered_at", None) is None:
        logger.info(
            "safe_send_message: user %s not registered (no /start), skipping",
            telegram_id,
        )
        return False

    try:
        await bot.send_message(telegram_id, text, **kwargs)
        return True
    except TelegramForbiddenError:
        logger.warning(
            "safe_send_message: user %s blocked or never started the bot, skipping",
            telegram_id,
        )
    except TelegramBadRequest as exc:
        if "chat not found" in str(exc).lower():
            logger.warning(
                "safe_send_message: chat not found for user %s, skipping",
                telegram_id,
            )
        else:
            raise
    return False
