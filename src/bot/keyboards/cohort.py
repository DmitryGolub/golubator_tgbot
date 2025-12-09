from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def cohort_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Список когорт", callback_data="cohort_list")
    kb.button(text="Добавить когорту", callback_data="cohort_create")
    kb.button(text="Изменить когорту", callback_data="cohort_update")
    kb.button(text="Удалить когорту", callback_data="cohort_delete")

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")

    kb.adjust(1)

    return kb.as_markup()