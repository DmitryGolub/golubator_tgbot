from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.rbac import (
    ConfirmDeleteRoleCB,
    DeleteRoleCB,
    EditPermsCB,
    RoleDetailCB,
    TogglePermCB,
)
from src.bot.keyboards.utils import truncate_button_text
from src.models.role import Permission, RoleModel


def roles_list_keyboard(roles: list[RoleModel]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for role in roles:
        kb.button(
            text=f"{role.display_name} ({role.name})",
            callback_data=RoleDetailCB(role_id=role.id).pack(),
        )
    kb.button(text="➕ Создать роль", callback_data="rbac_create_role")
    kb.button(text="⬅️ Назад", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def role_detail_keyboard(role: RoleModel, user_count: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🔑 Управление пермишенами",
        callback_data=EditPermsCB(role_id=role.id),
    )
    if user_count == 0:
        kb.button(
            text="🗑 Удалить роль",
            callback_data=DeleteRoleCB(role_id=role.id).pack(),
        )
    kb.button(text="⬅️ Назад", callback_data="menu_roles")
    kb.adjust(1)
    return kb.as_markup()


def permissions_keyboard(
    role: RoleModel,
    all_permissions: list[Permission],
) -> InlineKeyboardMarkup:
    role_perm_ids = {p.id for p in role.permissions}
    kb = InlineKeyboardBuilder()
    for perm in all_permissions:
        check = "✅" if perm.id in role_perm_ids else "❌"
        raw = f"{check} {perm.description}"
        kb.button(
            text=truncate_button_text(raw, 32),
            callback_data=TogglePermCB(role_id=role.id, perm_id=perm.id).pack(),
        )
    kb.button(text="⬅️ Назад", callback_data=RoleDetailCB(role_id=role.id).pack())
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_keyboard(role: RoleModel) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Да, удалить",
        callback_data=ConfirmDeleteRoleCB(role_id=role.id).pack(),
    )
    kb.button(
        text="❌ Отмена",
        callback_data=RoleDetailCB(role_id=role.id).pack(),
    )
    kb.adjust(2)
    return kb.as_markup()
