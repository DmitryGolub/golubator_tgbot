from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def user_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Список пользователей", callback_data="user_list")
    kb.button(text="Изменить пользователя", callback_data="user_update")

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")

    kb.adjust(1)

    return kb.as_markup()
