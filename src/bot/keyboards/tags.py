from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.tags import (
    TagActionCB,
    TagAssignTagCB,
    TagAssignUserCB,
    TagConfirmDeleteCB,
    TagDeleteCB,
    TagUnassignCB,
    TagUnassignUserCB,
)
from src.models.tag import Tag
from src.models.user import User


def tags_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Список тегов", callback_data=TagActionCB(action="list"))
    builder.button(text="Создать тег", callback_data=TagActionCB(action="create"))
    builder.button(text="Назначить тег", callback_data=TagActionCB(action="assign"))
    builder.button(text="Снять тег", callback_data=TagActionCB(action="unassign"))
    builder.button(text="⬅️ Назад", callback_data="menu_users")
    builder.adjust(1)
    return builder.as_markup()


def tags_list_keyboard(tags: list[Tag]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tag in tags:
        builder.button(
            text=f"❌ {tag.name}",
            callback_data=TagDeleteCB(tag_id=tag.id),
        )
    builder.button(text="⬅️ Назад", callback_data="menu_tags")
    builder.adjust(1)
    return builder.as_markup()


def tag_assign_users_keyboard(users: list[User]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        builder.button(
            text=f"{user.name} @{user.username}",
            callback_data=TagAssignUserCB(user_id=user.telegram_id),
        )
    builder.button(text="⬅️ Назад", callback_data="menu_tags")
    builder.adjust(1)
    return builder.as_markup()


def tag_select_for_assign_keyboard(
    user_id: int, tags: list[Tag]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tag in tags:
        builder.button(
            text=tag.name,
            callback_data=TagAssignTagCB(user_id=user_id, tag_id=tag.id),
        )
    builder.button(text="⬅️ Назад", callback_data="menu_tags")
    builder.adjust(1)
    return builder.as_markup()


def tag_unassign_users_keyboard(users: list[User]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        tags_str = ", ".join(t.name for t in user.tags) if user.tags else "—"
        builder.button(
            text=f"{user.name} [{tags_str}]",
            callback_data=TagUnassignUserCB(user_id=user.telegram_id),
        )
    builder.button(text="⬅️ Назад", callback_data="menu_tags")
    builder.adjust(1)
    return builder.as_markup()


def tag_select_for_unassign_keyboard(
    user_id: int, tags: list[Tag]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tag in tags:
        builder.button(
            text=tag.name,
            callback_data=TagUnassignCB(user_id=user_id, tag_id=tag.id),
        )
    builder.button(text="⬅️ Назад", callback_data="menu_tags")
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_tag_keyboard(tag_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить", callback_data=TagConfirmDeleteCB(tag_id=tag_id))
    builder.button(text="Отмена", callback_data="menu_tags")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="menu_tags")
    builder.adjust(1)
    return builder.as_markup()
