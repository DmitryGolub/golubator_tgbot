from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Пользователи", callback_data="menu_users")
    kb.button(text="Когорты", callback_data="menu_cohorts")
    kb.button(text="Рассылки", callback_data="menu_mailings")

    kb.adjust(1)

    return kb.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")

    kb.adjust(1)

    return kb.as_markup()

