import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.exc import IntegrityError

from src.bot.callbacks.tags import (
    TagActionCB,
    TagAssignTagCB,
    TagAssignUserCB,
    TagDeleteCB,
    TagUnassignCB,
    TagUnassignUserCB,
)
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.tags import (
    cancel_keyboard,
    tag_assign_users_keyboard,
    tag_select_for_assign_keyboard,
    tag_select_for_unassign_keyboard,
    tag_unassign_users_keyboard,
    tags_list_keyboard,
    tags_menu_keyboard,
)
from src.bot.states.tags import CreateTagFSM
from src.dao.tag import TagDAO
from src.dao.user import UserDAO
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="tags")
router.message.filter(PermissionFilter("manage_users"))
router.callback_query.filter(PermissionFilter("manage_users"))


# --- Menu ---


@router.callback_query(F.data == "menu_tags")
async def cb_tags_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    try:
        await callback.message.edit_text(
            "Управление тегами", reply_markup=tags_menu_keyboard()
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


# --- List ---


@router.callback_query(TagActionCB.filter(F.action == "list"))
async def cb_tags_list(callback: CallbackQuery):
    await callback.answer()
    tags = await TagDAO.get_all()
    if not tags:
        await callback.message.edit_text(
            "Тегов пока нет.", reply_markup=tags_menu_keyboard()
        )
        return
    await callback.message.edit_text(
        "Список тегов (нажмите ❌ для удаления):",
        reply_markup=tags_list_keyboard(tags),
    )


# --- Create ---


@router.callback_query(TagActionCB.filter(F.action == "create"))
async def cb_tag_create(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(CreateTagFSM.waiting_name)
    await callback.message.edit_text(
        "Введите имя нового тега:", reply_markup=cancel_keyboard()
    )


@router.message(CreateTagFSM.waiting_name)
async def on_tag_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя тега не может быть пустым. Попробуйте ещё раз:")
        return

    try:
        tag = await TagDAO.add(name=name)
    except IntegrityError:
        logger.warning("Tag already exists: %s", name)
        await state.clear()
        await message.answer(
            f"Тег <b>{e(name)}</b> уже существует.",
            reply_markup=tags_menu_keyboard(),
        )
        return

    logger.info("Tag created: %s (id=%s)", tag.name, tag.id)
    await state.clear()
    await message.answer(
        f"Тег <b>{e(tag.name)}</b> создан.",
        reply_markup=tags_menu_keyboard(),
    )


# --- Delete ---


@router.callback_query(TagDeleteCB.filter())
async def cb_tag_delete(callback: CallbackQuery, callback_data: TagDeleteCB):
    await callback.answer()
    await TagDAO.delete(id=callback_data.tag_id)
    logger.info("Tag deleted: id=%s", callback_data.tag_id)
    tags = await TagDAO.get_all()
    if not tags:
        await callback.message.edit_text(
            "Все теги удалены.", reply_markup=tags_menu_keyboard()
        )
        return
    await callback.message.edit_text(
        "Тег удалён. Список тегов:",
        reply_markup=tags_list_keyboard(tags),
    )


# --- Assign ---


@router.callback_query(TagActionCB.filter(F.action == "assign"))
async def cb_tag_assign_select_user(callback: CallbackQuery):
    await callback.answer()
    users = await UserDAO.get_all()
    if not users:
        await callback.message.edit_text(
            "Пользователей нет.", reply_markup=tags_menu_keyboard()
        )
        return
    await callback.message.edit_text(
        "Выберите пользователя для назначения тега:",
        reply_markup=tag_assign_users_keyboard(users),
    )


@router.callback_query(TagAssignUserCB.filter())
async def cb_tag_assign_select_tag(
    callback: CallbackQuery, callback_data: TagAssignUserCB
):
    await callback.answer()
    tags = await TagDAO.get_all()
    if not tags:
        await callback.message.edit_text(
            "Тегов нет. Сначала создайте тег.", reply_markup=tags_menu_keyboard()
        )
        return
    await callback.message.edit_text(
        "Выберите тег для назначения:",
        reply_markup=tag_select_for_assign_keyboard(callback_data.user_id, tags),
    )


@router.callback_query(TagAssignTagCB.filter())
async def cb_tag_assign_confirm(callback: CallbackQuery, callback_data: TagAssignTagCB):
    await callback.answer()
    user = await UserDAO.assign_tag(
        telegram_id=callback_data.user_id,
        tag_id=callback_data.tag_id,
    )
    if not user:
        await callback.message.edit_text(
            "Пользователь или тег не найден.",
            reply_markup=tags_menu_keyboard(),
        )
        return

    logger.info(
        "Tag assigned: user=%s tag_id=%s", callback_data.user_id, callback_data.tag_id
    )
    tags_str = ", ".join(t.name for t in user.tags) if user.tags else "—"
    await callback.message.edit_text(
        f"Тег назначен.\n\n"
        f"<b>{e(user.name)}</b> @{e(user.username)}\n"
        f"Теги: {e(tags_str)}",
        reply_markup=tags_menu_keyboard(),
    )


# --- Unassign ---


@router.callback_query(TagActionCB.filter(F.action == "unassign"))
async def cb_tag_unassign_select_user(callback: CallbackQuery):
    await callback.answer()
    users = await UserDAO.get_all()
    users_with_tags = [u for u in users if u.tags]
    if not users_with_tags:
        await callback.message.edit_text(
            "Нет пользователей с тегами.",
            reply_markup=tags_menu_keyboard(),
        )
        return
    await callback.message.edit_text(
        "Выберите пользователя для снятия тега:",
        reply_markup=tag_unassign_users_keyboard(users_with_tags),
    )


@router.callback_query(TagUnassignUserCB.filter())
async def cb_tag_unassign_select_tag(
    callback: CallbackQuery, callback_data: TagUnassignUserCB
):
    await callback.answer()
    users = await UserDAO.get_all(telegram_id=callback_data.user_id)
    user = users[0] if users else None
    if not user or not user.tags:
        await callback.message.edit_text(
            "У пользователя нет тегов.",
            reply_markup=tags_menu_keyboard(),
        )
        return
    await callback.message.edit_text(
        f"Выберите тег для снятия с <b>{e(user.name)}</b>:",
        reply_markup=tag_select_for_unassign_keyboard(callback_data.user_id, user.tags),
    )


@router.callback_query(TagUnassignCB.filter())
async def cb_tag_unassign_confirm(
    callback: CallbackQuery, callback_data: TagUnassignCB
):
    await callback.answer()
    user = await UserDAO.unassign_tag(
        telegram_id=callback_data.user_id,
        tag_id=callback_data.tag_id,
    )
    if not user:
        await callback.message.edit_text(
            "Пользователь не найден.",
            reply_markup=tags_menu_keyboard(),
        )
        return

    logger.info(
        "Tag unassigned: user=%s tag_id=%s", callback_data.user_id, callback_data.tag_id
    )
    tags_str = ", ".join(t.name for t in user.tags) if user.tags else "—"
    await callback.message.edit_text(
        f"Тег снят.\n\n<b>{e(user.name)}</b> @{e(user.username)}\nТеги: {e(tags_str)}",
        reply_markup=tags_menu_keyboard(),
    )
