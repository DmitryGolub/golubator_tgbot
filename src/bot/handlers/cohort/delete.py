import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.bot.callbacks.cohort import (
    ConfirmDeleteTypeCB,
    DeleteCohortTypeCB,
    DeleteOptionCB,
)
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.cohort import cohort_confirm_delete_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.services.notion_client import get_notion_service
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="cohort-delete")
router.callback_query.filter(PermissionFilter("manage_cohorts"))


# === Delete cohort type (show confirmation) ===


@router.callback_query(DeleteCohortTypeCB.filter())
async def confirm_delete_type(
    callback: CallbackQuery, callback_data: DeleteCohortTypeCB, state: FSMContext
):
    await callback.answer()

    data = await state.get_data()
    types_map = data.get("cohort_types_map", {})
    type_name = types_map.get(str(callback_data.idx))
    if not type_name:
        await callback.message.edit_text(
            "Тип когорты не найден. Попробуйте снова.",
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        f'Вы уверены, что хотите удалить тип когорты "<b>{e(type_name)}</b>"?\n'
        f"Это удалит свойство и данные у всех страниц в Notion!",
        reply_markup=cohort_confirm_delete_keyboard(callback_data.idx),
    )


@router.callback_query(ConfirmDeleteTypeCB.filter())
async def do_delete_type(
    callback: CallbackQuery, callback_data: ConfirmDeleteTypeCB, state: FSMContext
):
    await callback.answer()

    data = await state.get_data()
    types_map = data.get("cohort_types_map", {})
    type_name = types_map.get(str(callback_data.idx))
    if not type_name:
        await callback.message.edit_text(
            "Тип когорты не найден. Попробуйте снова.",
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    notion = get_notion_service()
    if not notion:
        await callback.message.edit_text(
            "Notion не настроен.", reply_markup=await back_to_menu_keyboard()
        )
        return

    try:
        success = await notion.delete_cohort_type(type_name)
    finally:
        await notion.close()

    if success:
        logger.info("Cohort type deleted: %s", type_name)
        await callback.message.edit_text(
            f'Тип когорты "<b>{e(type_name)}</b>" удалён из Notion.',
            reply_markup=await back_to_menu_keyboard(),
        )
    else:
        logger.warning("Failed to delete cohort type: %s", type_name)
        await callback.message.edit_text(
            f'Не удалось удалить тип "{e(type_name)}". Возможно, он защищён.',
            reply_markup=await back_to_menu_keyboard(),
        )


# === Delete option ===


@router.callback_query(DeleteOptionCB.filter())
async def delete_option(
    callback: CallbackQuery, callback_data: DeleteOptionCB, state: FSMContext
):
    await callback.answer()

    data = await state.get_data()
    options_map = data.get("cohort_options_map", {})
    type_name = data.get("current_type_name")
    option_name = options_map.get(str(callback_data.idx))

    if not type_name or not option_name:
        await callback.message.edit_text(
            "Данные устарели. Попробуйте снова.",
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    notion = get_notion_service()
    if not notion:
        await callback.message.edit_text(
            "Notion не настроен.", reply_markup=await back_to_menu_keyboard()
        )
        return

    try:
        success = await notion.remove_option(type_name, option_name)
    finally:
        await notion.close()

    if success:
        await callback.message.edit_text(
            f'Опция "<b>{e(option_name)}</b>" удалена из <b>{e(type_name)}</b>.',
            reply_markup=await back_to_menu_keyboard(),
        )
    else:
        await callback.message.edit_text(
            f'Не удалось удалить опцию "{e(option_name)}".',
            reply_markup=await back_to_menu_keyboard(),
        )
