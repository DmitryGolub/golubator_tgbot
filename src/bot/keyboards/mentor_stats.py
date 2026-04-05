from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.mentor_stats import MentorStatsCB
from src.bot.keyboards.pagination import get_page_slice, paginate_buttons
from src.bot.keyboards.utils import format_user_label
from src.models.mentor import Mentor


def mentor_select_keyboard(
    mentors: list[Mentor], page: int = 0
) -> InlineKeyboardMarkup:
    page_items, total_pages = get_page_slice(mentors, page)
    builder = InlineKeyboardBuilder()

    nav = paginate_buttons("mstats", page, total_pages)
    if nav:
        builder.row(*nav)

    for m in page_items:
        username = m.user.username if m.user and m.user.username else None
        builder.row(
            InlineKeyboardButton(
                text=format_user_label(m.name, username),
                callback_data=MentorStatsCB(mentor_id=m.telegram_id).pack(),
            )
        )

    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
    return builder.as_markup()
