from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def caldav_status_keyboard(
    *, has_account: bool, sync_enabled: bool
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not has_account:
        kb.button(text="🔗 Подключить", callback_data="caldav_connect")
    else:
        kb.button(text="♻️ Переподключить", callback_data="caldav_connect")
        kb.button(text="🔍 Проверить", callback_data="caldav_verify")
        if sync_enabled:
            kb.button(text="⏸ Отключить", callback_data="caldav_disable")
        else:
            kb.button(text="▶️ Включить", callback_data="caldav_enable")
    kb.button(text="⬅️ В меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def caldav_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="caldav_cancel")
    kb.adjust(1)
    return kb.as_markup()
