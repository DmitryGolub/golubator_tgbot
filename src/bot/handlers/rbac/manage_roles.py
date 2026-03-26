import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks.rbac import (
    ConfirmDeleteRoleCB,
    DeleteRoleCB,
    RoleDetailCB,
    TogglePermCB,
)
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.rbac import (
    bool_keyboard,
    confirm_delete_keyboard,
    permissions_keyboard,
    role_detail_keyboard,
    roles_list_keyboard,
)
from src.bot.states.rbac import CreateRoleFSM
from src.dao.role import PermissionDAO, RoleDAO
from src.services.auth import AuthService
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="rbac")
router.message.filter(PermissionFilter("manage_roles"))
router.callback_query.filter(PermissionFilter("manage_roles"))

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


@router.callback_query(F.data == "menu_roles")
async def cb_roles_list(callback: CallbackQuery):
    await callback.answer()
    roles = await RoleDAO.get_all()
    await callback.message.edit_text(
        "<b>Управление ролями</b>",
        reply_markup=roles_list_keyboard(roles),
    )


@router.callback_query(RoleDetailCB.filter())
async def cb_role_detail(callback: CallbackQuery, callback_data: RoleDetailCB):
    await callback.answer()
    role = await RoleDAO.get_with_permissions(callback_data.role_id)
    if not role:
        await callback.message.edit_text("Роль не найдена.")
        return

    user_count = await RoleDAO.count_users(role.id)
    perm_names = ", ".join(e(p.codename) for p in role.permissions) or "нет"
    flags = []
    if role.is_mentor:
        flags.append("менторская")
    if role.is_student:
        flags.append("студенческая")
    flags_text = ", ".join(flags) or "нет"

    text = (
        f"<b>Роль: {e(role.display_name)}</b> (<code>{e(role.name)}</code>)\n\n"
        f"Флаги: {flags_text}\n"
        f"Пользователей: {user_count}\n"
        f"Пермишены: {perm_names}"
    )
    await callback.message.edit_text(
        text, reply_markup=role_detail_keyboard(role, user_count)
    )


# ── Permissions toggle ──


@router.callback_query(F.data.startswith("rbac_edit_perms:"))
async def cb_edit_perms(callback: CallbackQuery):
    await callback.answer()
    role_id = int(callback.data.split(":")[1])
    role = await RoleDAO.get_with_permissions(role_id)
    if not role:
        await callback.message.edit_text("Роль не найдена.")
        return

    all_perms = await PermissionDAO.get_all()
    await callback.message.edit_text(
        f"<b>Пермишены роли {e(role.display_name)}</b>",
        reply_markup=permissions_keyboard(role, all_perms),
    )


@router.callback_query(TogglePermCB.filter())
async def cb_toggle_perm(callback: CallbackQuery, callback_data: TogglePermCB):
    await callback.answer()
    role = await RoleDAO.get_with_permissions(callback_data.role_id)
    if not role:
        await callback.message.edit_text("Роль не найдена.")
        return

    has_perm = any(p.id == callback_data.perm_id for p in role.permissions)
    if has_perm:
        await RoleDAO.remove_permission(callback_data.role_id, callback_data.perm_id)
        logger.info(
            "Permission removed: role=%s perm_id=%s", role.name, callback_data.perm_id
        )
    else:
        await RoleDAO.add_permission(callback_data.role_id, callback_data.perm_id)
        logger.info(
            "Permission added: role=%s perm_id=%s", role.name, callback_data.perm_id
        )

    await AuthService.invalidate_role(callback_data.role_id)

    role = await RoleDAO.get_with_permissions(callback_data.role_id)
    all_perms = await PermissionDAO.get_all()
    await callback.message.edit_text(
        f"<b>Пермишены роли {e(role.display_name)}</b>",
        reply_markup=permissions_keyboard(role, all_perms),
    )


# ── Delete role ──


@router.callback_query(DeleteRoleCB.filter())
async def cb_delete_role(callback: CallbackQuery, callback_data: DeleteRoleCB):
    await callback.answer()
    role = await RoleDAO.find_one_or_none(id=callback_data.role_id)
    if not role:
        await callback.message.edit_text("Роль не найдена.")
        return

    await callback.message.edit_text(
        f"Удалить роль <b>{e(role.display_name)}</b>?",
        reply_markup=confirm_delete_keyboard(role),
    )


@router.callback_query(ConfirmDeleteRoleCB.filter())
async def cb_confirm_delete(
    callback: CallbackQuery, callback_data: ConfirmDeleteRoleCB
):
    await callback.answer()
    user_count = await RoleDAO.count_users(callback_data.role_id)
    if user_count > 0:
        await callback.message.edit_text(
            "Нельзя удалить роль, к которой привязаны пользователи."
        )
        return

    await RoleDAO.delete(id=callback_data.role_id)
    logger.info("Role deleted: role_id=%s", callback_data.role_id)
    roles = await RoleDAO.get_all()
    await callback.message.edit_text(
        "Роль удалена.",
        reply_markup=roles_list_keyboard(roles),
    )


# ── Create role FSM ──


@router.callback_query(F.data == "rbac_create_role")
async def cb_create_role_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(CreateRoleFSM.waiting_name)
    await callback.message.edit_text(
        "Введите системное имя роли (латиница, snake_case, например: <code>senior_mentor</code>):\n\n"
        "Отправьте /cancel для отмены."
    )


@router.message(StateFilter(CreateRoleFSM), F.text == "/cancel")
async def msg_cancel_create_role(message: Message, state: FSMContext):
    await state.clear()
    roles = await RoleDAO.get_all()
    await message.answer(
        "Создание роли отменено.",
        reply_markup=roles_list_keyboard(roles),
    )


@router.message(StateFilter(CreateRoleFSM.waiting_name))
async def msg_role_name(message: Message, state: FSMContext):
    name = (message.text or "").strip().lower()
    if not NAME_PATTERN.match(name):
        await message.answer(
            "Имя должно быть 2-49 символов, только латиница, цифры и _ (начинается с буквы)."
        )
        return

    existing = await RoleDAO.get_by_name(name)
    if existing:
        await message.answer(
            f"Роль <code>{e(name)}</code> уже существует. Введите другое имя."
        )
        return

    await state.update_data(name=name)
    await state.set_state(CreateRoleFSM.waiting_display_name)
    await message.answer(
        "Введите отображаемое название роли (например: Старший ментор):"
    )


@router.message(StateFilter(CreateRoleFSM.waiting_display_name))
async def msg_role_display_name(message: Message, state: FSMContext):
    display_name = (message.text or "").strip()
    if not display_name or len(display_name) > 100:
        await message.answer("Название должно быть от 1 до 100 символов.")
        return

    await state.update_data(display_name=display_name)
    await state.set_state(CreateRoleFSM.waiting_is_mentor)
    await message.answer(
        "Это менторская роль? (пользователи с этой ролью будут считаться менторами в созвонах)",
        reply_markup=bool_keyboard("rbac_is_mentor"),
    )


@router.callback_query(
    StateFilter(CreateRoleFSM.waiting_is_mentor),
    F.data.startswith("rbac_is_mentor:"),
)
async def cb_is_mentor(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    is_mentor = callback.data.endswith(":yes")
    await state.update_data(is_mentor=is_mentor)
    await state.set_state(CreateRoleFSM.waiting_is_student)
    await callback.message.edit_text(
        "Это студенческая роль? (пользователи с этой ролью будут считаться учениками в созвонах)",
        reply_markup=bool_keyboard("rbac_is_student"),
    )


@router.callback_query(
    StateFilter(CreateRoleFSM.waiting_is_student),
    F.data.startswith("rbac_is_student:"),
)
async def cb_is_student(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    is_student = callback.data.endswith(":yes")
    data = await state.get_data()
    await state.clear()

    role = await RoleDAO.add(
        name=data["name"],
        display_name=data["display_name"],
        is_mentor=data["is_mentor"],
        is_student=is_student,
    )
    logger.info("Role created: %s (%s)", role.name, role.display_name)

    roles = await RoleDAO.get_all()
    await callback.message.edit_text(
        f"Роль <b>{e(role.display_name)}</b> (<code>{e(role.name)}</code>) создана.",
        reply_markup=roles_list_keyboard(roles),
    )
