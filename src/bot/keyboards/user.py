from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData

from src.models.user import User

from src.bot.callback.user import UserAction, UserActionSelectCB, UserActionUserCB

class UserDetailCB(CallbackData, prefix="user"):
    user_id: int


def user_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Список пользователей", callback_data="user_list")
    kb.button(text="Изменить пользователя", callback_data="user_update_menu")

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")

    kb.adjust(1)

    return kb.as_markup()


def user_update_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Обновить роль", callback_data=UserActionSelectCB(action=UserAction.update_role).pack())
    kb.button(text="Обновить состояние", callback_data=UserActionSelectCB(action=UserAction.update_state).pack())
    kb.button(text="Обновить ментора", callback_data=UserActionSelectCB(action=UserAction.update_mentor).pack())

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")

    kb.adjust(1)

    return kb.as_markup()


def users_for_action_keyboard(users: list[User], action: UserAction) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for user in users:
        kb.button(
            text=user.name or user.username or f"User {user.telegram_id}",
            callback_data=UserActionUserCB(
                action=action,
                user_id=user.telegram_id,
            ).pack(),
        )

    kb.adjust(1)
    return kb.as_markup()
