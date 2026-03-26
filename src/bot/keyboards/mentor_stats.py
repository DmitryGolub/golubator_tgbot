from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.mentor_stats import MentorStatsCB
from src.models.mentor import Mentor


def mentor_select_keyboard(mentors: list[Mentor]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for m in mentors:
        username = f" @{m.user.username}" if m.user and m.user.username else ""
        builder.button(
            text=f"{m.name}{username}",
            callback_data=MentorStatsCB(mentor_id=m.telegram_id),
        )
    builder.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()
