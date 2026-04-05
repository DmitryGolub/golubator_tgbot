from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def job_search_period_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="За неделю", callback_data="job_search_period:week")
    kb.button(text="За месяц", callback_data="job_search_period:month")
    kb.button(text="За всё время", callback_data="job_search_period:all")
    kb.button(text="⬅️ Назад", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()
