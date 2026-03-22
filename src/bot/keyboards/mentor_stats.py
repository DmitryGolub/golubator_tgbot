from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.mentor_stats import MentorStatsCB
from src.models.user import User


def mentor_select_keyboard(mentors: list[User]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for m in mentors:
        builder.button(
            text=f"{m.name} @{m.username}",
            callback_data=MentorStatsCB(mentor_id=m.telegram_id),
        )
    builder.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()
