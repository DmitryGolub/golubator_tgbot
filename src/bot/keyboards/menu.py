from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from src.models.user import Role


def menu_keyboard(role: Role) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if role == Role.admin:
        kb.button(text="Пользователи", callback_data="menu_users")
        kb.button(text="Когорты", callback_data="menu_cohorts")
        kb.button(text="Рассылки", callback_data="menu_mailings")
    elif role == Role.mentor:
        kb.button(text="Ученики", callback_data="mentor_students_menu")
        kb.button(text="Созвоны", callback_data="mentor_meetings_menu")
        kb.button(text="Обо мне", callback_data="mentor_me_info")
    elif role == Role.student:
        kb.button(text="Назначенные созвоны", callback_data="student_meetings")
        kb.button(text="Информация обо мне", callback_data="student_me_info")

    kb.adjust(1)

    return kb.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")

    kb.adjust(1)

    return kb.as_markup()

