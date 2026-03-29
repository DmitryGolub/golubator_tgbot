from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.update_user import (
    UpdateParam,
    ChooseParamCB,
    ChooseEnumValueCB,
    ChooseMentorCB,
    ChooseUserCB,
    ChooseMenteeCB,
    ChooseCohortTypeCB,
)
from src.bot.keyboards.pagination import get_page_slice, paginate_buttons
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
    kb.button(
        text="📋 Обновить когорту",
        callback_data=ChooseParamCB(param=UpdateParam.COHORT).pack(),
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


async def cohort_types_keyboard() -> InlineKeyboardMarkup:
    from src.dao.cohort import CohortDAO

    types = await CohortDAO.get_distinct_types()
    kb = InlineKeyboardBuilder()

    for cohort_type in types:
        if cohort_type == "Status":
            continue
        kb.button(
            text=cohort_type,
            callback_data=ChooseCohortTypeCB(cohort_type=cohort_type).pack(),
        )

    kb.adjust(1)
    return kb.as_markup()


async def cohort_values_keyboard(cohort_type: str) -> InlineKeyboardMarkup:
    from src.dao.cohort import CohortDAO

    values = await CohortDAO.get_distinct_values(cohort_type)
    kb = InlineKeyboardBuilder()

    for value in values:
        kb.button(
            text=value,
            callback_data=ChooseEnumValueCB(
                param=UpdateParam.COHORT,
                value=value,
            ).pack(),
        )

    kb.adjust(1)
    return kb.as_markup()


async def user_list_paginated_keyboard(
    total_pages: int,
    page: int = 0,
) -> InlineKeyboardMarkup:
    from src.services.ui_text import UiTextService

    texts = await UiTextService.get_many(["user.btn.update", "menu.back"])
    kb = InlineKeyboardBuilder()

    nav = paginate_buttons("user_list", page, total_pages)
    if nav:
        kb.row(*nav)

    kb.row(
        InlineKeyboardButton(
            text=texts["user.btn.update"], callback_data="user_update_menu"
        )
    )
    kb.row(InlineKeyboardButton(text=texts["menu.back"], callback_data="back_to_menu"))
    return kb.as_markup()


def mentors_keyboard(mentors: Sequence[User], page: int = 0) -> InlineKeyboardMarkup:
    page_items, total_pages = get_page_slice(mentors, page)
    kb = InlineKeyboardBuilder()

    nav = paginate_buttons("mentors", page, total_pages)
    if nav:
        kb.row(*nav)

    for mentor in page_items:
        kb.row(
            InlineKeyboardButton(
                text=f"{mentor.name}"
                + (f" @{mentor.username}" if mentor.username else ""),
                callback_data=ChooseMentorCB(mentor_id=mentor.telegram_id).pack(),
            )
        )

    return kb.as_markup()


def mentees_keyboard(mentees: Sequence, page: int = 0) -> InlineKeyboardMarkup:
    page_items, total_pages = get_page_slice(mentees, page)
    kb = InlineKeyboardBuilder()

    nav = paginate_buttons("mentees", page, total_pages)
    if nav:
        kb.row(*nav)

    for mentee in page_items:
        display_name = getattr(mentee, "doc_name", None) or mentee.name
        username = None
        if hasattr(mentee, "user") and mentee.user:
            username = mentee.user.username
        label = f"{display_name} @{username}" if username else display_name
        kb.row(
            InlineKeyboardButton(
                text=label,
                callback_data=ChooseMenteeCB(mentee_id=mentee.id).pack(),
            )
        )

    return kb.as_markup()


def users_keyboard(users: Sequence[User], page: int = 0) -> InlineKeyboardMarkup:
    page_items, total_pages = get_page_slice(users, page)
    kb = InlineKeyboardBuilder()

    nav = paginate_buttons("users", page, total_pages)
    if nav:
        kb.row(*nav)

    for user in page_items:
        kb.row(
            InlineKeyboardButton(
                text=f"{user.name}" + (f" @{user.username}" if user.username else ""),
                callback_data=ChooseUserCB(user_id=user.telegram_id).pack(),
            )
        )

    return kb.as_markup()
