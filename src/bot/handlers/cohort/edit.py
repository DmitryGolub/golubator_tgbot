import logging

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks.cohort import RenameCohortTypeCB, RenameOptionCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.cohort import cohort_cancel_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.states.cohort import CohortTypeFSM
from src.bot.utils import safe_edit_text
from src.services.notion_client import get_notion_service
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="cohort-edit")
router.message.filter(PermissionFilter("manage_cohorts"))
router.callback_query.filter(PermissionFilter("manage_cohorts"))


# === Rename cohort type ===


@router.callback_query(RenameCohortTypeCB.filter())
async def start_rename_type(
    callback: CallbackQuery, callback_data: RenameCohortTypeCB, state: FSMContext
):
    await callback.answer()

    data = await state.get_data()
    types_map = data.get("cohort_types_map", {})
    type_name = types_map.get(str(callback_data.idx))
    if not type_name:
        await safe_edit_text(
            callback,
            "Тип когорты не найден. Попробуйте снова.",
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    await state.set_state(CohortTypeFSM.waiting_rename_type)
    await state.update_data(old_type_name=type_name)
    await safe_edit_text(
        callback,
        f'Введите новое название для типа когорты "<b>{e(type_name)}</b>":',
        reply_markup=cohort_cancel_keyboard(),
    )


@router.message(StateFilter(CohortTypeFSM.waiting_rename_type))
async def process_rename_type(message: Message, state: FSMContext):
    new_name = message.text.strip() if message.text else ""
    if not new_name:
        await message.answer(
            "Название не может быть пустым.",
            reply_markup=cohort_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    old_name = data.get("old_type_name", "")

    notion = get_notion_service()
    if not notion:
        await state.clear()
        await message.answer(
            "Notion не настроен.", reply_markup=await back_to_menu_keyboard()
        )
        return

    try:
        success = await notion.rename_cohort_type(old_name, new_name)
    except Exception:
        logger.exception("Notion API error renaming cohort type %s", old_name)
        success = False
    finally:
        await notion.close()
        await state.clear()

    if success:
        logger.info("Cohort type renamed: %s -> %s", old_name, new_name)
        await message.answer(
            f'Тип когорты переименован: "<b>{e(old_name)}</b>" → "<b>{e(new_name)}</b>".',
            reply_markup=await back_to_menu_keyboard(),
        )
    else:
        logger.warning("Failed to rename cohort type: %s", old_name)
        await message.answer(
            f'Не удалось переименовать тип "{e(old_name)}". Возможно, он защищён.',
            reply_markup=await back_to_menu_keyboard(),
        )


# === Rename option ===


@router.callback_query(RenameOptionCB.filter())
async def start_rename_option(
    callback: CallbackQuery, callback_data: RenameOptionCB, state: FSMContext
):
    await callback.answer()

    data = await state.get_data()
    options_map = data.get("cohort_options_map", {})
    type_name = data.get("current_type_name")
    option_name = options_map.get(str(callback_data.idx))

    if not type_name or not option_name:
        await safe_edit_text(
            callback,
            "Данные устарели. Попробуйте снова.",
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    await state.set_state(CohortTypeFSM.waiting_rename_option)
    await state.update_data(
        rename_type_name=type_name,
        rename_old_option=option_name,
    )
    await safe_edit_text(
        callback,
        f'Введите новое название для опции "<b>{e(option_name)}</b>" '
        f"в <b>{e(type_name)}</b>:",
        reply_markup=cohort_cancel_keyboard(),
    )


@router.message(StateFilter(CohortTypeFSM.waiting_rename_option))
async def process_rename_option(message: Message, state: FSMContext):
    new_name = message.text.strip() if message.text else ""
    if not new_name:
        await message.answer(
            "Название не может быть пустым.",
            reply_markup=cohort_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    type_name = data.get("rename_type_name", "")
    old_option = data.get("rename_old_option", "")

    notion = get_notion_service()
    if not notion:
        await state.clear()
        await message.answer(
            "Notion не настроен.", reply_markup=await back_to_menu_keyboard()
        )
        return

    try:
        success = await notion.rename_option(type_name, old_option, new_name)
    except Exception:
        logger.exception(
            "Notion API error renaming option %s in %s", old_option, type_name
        )
        success = False
    finally:
        await notion.close()
        await state.clear()

    if success:
        await message.answer(
            f'Опция переименована: "<b>{e(old_option)}</b>" → "<b>{e(new_name)}</b>" в <b>{e(type_name)}</b>.',
            reply_markup=await back_to_menu_keyboard(),
        )
    else:
        await message.answer(
            f'Не удалось переименовать опцию "{e(old_option)}".',
            reply_markup=await back_to_menu_keyboard(),
        )
