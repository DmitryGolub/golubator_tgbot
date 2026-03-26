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
from src.models.user import User


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


async def statuses_keyboard() -> InlineKeyboardMarkup:
    from src.dao.cohort import CohortDAO

    values = await CohortDAO.get_distinct_values("Status")
    kb = InlineKeyboardBuilder()

    for status_value in values:
        kb.button(
            text=status_value,
            callback_data=ChooseEnumValueCB(
                param=UpdateParam.STATUS,
                value=status_value,
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
