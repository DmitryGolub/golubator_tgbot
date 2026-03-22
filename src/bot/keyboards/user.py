from collections.abc import Sequence

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from src.bot.callbacks.update_user import (
    UpdateParam,
    ChooseParamCB,
    ChooseEnumValueCB,
    ChooseMentorCB,
    ChooseUserCB,
)
from src.models.user import State, User


def user_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Список пользователей", callback_data="user_list")
    kb.button(text="Изменить пользователя", callback_data="user_update_menu")
    kb.button(text="Теги", callback_data="menu_tags")

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")

    kb.adjust(1)

    return kb.as_markup()


def update_param_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(
        text="🔄 Обновить статус",
        callback_data=ChooseParamCB(param=UpdateParam.STATUS).pack(),
    )
    kb.button(
        text="🛡 Обновить роль",
        callback_data=ChooseParamCB(param=UpdateParam.ROLE).pack(),
    )
    kb.button(
        text="👨‍🏫 Обновить ментора",
        callback_data=ChooseParamCB(param=UpdateParam.MENTOR).pack(),
    )

    kb.adjust(1)
    return kb.as_markup()


def update_param_keyboard_for_mentor() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(
        text="🔄 Обновить статус ученика",
        callback_data=ChooseParamCB(param=UpdateParam.STATUS).pack(),
    )

    kb.adjust(1)
    return kb.as_markup()


async def roles_keyboard() -> InlineKeyboardMarkup:
    from src.dao.role import RoleDAO

    roles = await RoleDAO.get_all()
    kb = InlineKeyboardBuilder()
    for role in roles:
        kb.button(
            text=role.display_name,
            callback_data=ChooseEnumValueCB(
                param=UpdateParam.ROLE,
                value=role.name,
            ).pack(),
        )
    kb.adjust(1)
    return kb.as_markup()


def statuses_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for status in State:
        kb.button(
            text=status.value,
            callback_data=ChooseEnumValueCB(
                param=UpdateParam.STATUS,
                value=status.name,
            ).pack(),
        )

    kb.adjust(1)
    return kb.as_markup()


def mentors_keyboard(mentors: Sequence[User]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for mentor in mentors:
        kb.button(
            text=f"{mentor.name} {mentor.username}",
            callback_data=ChooseMentorCB(mentor_id=mentor.telegram_id).pack(),
        )

    kb.adjust(1)
    return kb.as_markup()


def users_keyboard(users: Sequence[User]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for user in users:
        kb.button(
            text=f"{user.name} {user.username}",
            callback_data=ChooseUserCB(user_id=user.telegram_id).pack(),
        )

    kb.adjust(1)
    return kb.as_markup()
