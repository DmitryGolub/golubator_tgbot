from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def menu_keyboard(permissions: set[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if "manage_users" in permissions:
        kb.button(text="Пользователи", callback_data="menu_users")
    if "manage_cohorts" in permissions:
        kb.button(text="Когорты", callback_data="menu_cohorts")
    if "manage_mailings" in permissions:
        kb.button(text="Рассылки", callback_data="menu_mailings")
    if "manage_roles" in permissions:
        kb.button(text="Роли", callback_data="menu_roles")
    if "view_students" in permissions:
        kb.button(text="Ученики", callback_data="mentor_students_menu")
    if "manage_meetings" in permissions:
        kb.button(text="Созвоны", callback_data="mentor_meetings_menu")
    if "view_own_info" in permissions:
        kb.button(text="Обо мне", callback_data="mentor_me_info")
    if "view_own_meetings" in permissions and "manage_meetings" not in permissions:
        kb.button(text="Назначенные созвоны", callback_data="student_meetings")
    if "view_own_info" in permissions and "view_students" not in permissions:
        kb.button(text="Информация обо мне", callback_data="student_me_info")

    kb.adjust(1)
    return kb.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()
