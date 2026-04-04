import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks.cohort import CreateOptionCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.cohort import cohort_cancel_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.states.cohort import CohortTypeFSM
from src.bot.utils import safe_edit_text
from src.services.notion_client import get_notion_service
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="cohort-create")
router.message.filter(PermissionFilter("manage_cohorts"))
router.callback_query.filter(PermissionFilter("manage_cohorts"))


# === Create cohort type ===


@router.callback_query(F.data == "cohort_create_type")
async def start_create_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(CohortTypeFSM.waiting_type_name)
    await safe_edit_text(
        callback,
        "Введите название нового типа когорты (будет создано multi_select свойство в Notion):",
        reply_markup=cohort_cancel_keyboard(),
    )


@router.message(StateFilter(CohortTypeFSM.waiting_type_name))
async def process_type_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if not name:
        await message.answer(
            "Название не может быть пустым.",
            reply_markup=cohort_cancel_keyboard(),
        )
        return

    notion = get_notion_service()
    if not notion:
        await state.clear()
        await message.answer(
            "Notion не настроен.", reply_markup=await back_to_menu_keyboard()
        )
        return

    try:
        success = await notion.create_cohort_type(name)
    except Exception:
        logger.exception("Notion API error creating cohort type %s", name)
        success = False
    finally:
        await notion.close()
        await state.clear()

    if success:
        logger.info("Cohort type created: %s", name)
        await message.answer(
            f'Тип когорты "<b>{e(name)}</b>" создан в Notion.',
            reply_markup=await back_to_menu_keyboard(),
        )
    else:
        logger.warning("Failed to create cohort type: %s", name)
        await message.answer(
            f'Не удалось создать тип "{e(name)}". Проверьте логи.',
            reply_markup=await back_to_menu_keyboard(),
        )


# === Create option within type ===


@router.callback_query(CreateOptionCB.filter())
async def start_create_option(
    callback: CallbackQuery, callback_data: CreateOptionCB, state: FSMContext
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

    await state.set_state(CohortTypeFSM.waiting_option_name)
    await state.update_data(type_name=type_name)
    await safe_edit_text(
        callback,
        f"Введите название новой опции для <b>{e(type_name)}</b>:",
        reply_markup=cohort_cancel_keyboard(),
    )


@router.message(StateFilter(CohortTypeFSM.waiting_option_name))
async def process_option_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if not name:
        await message.answer(
            "Название не может быть пустым.",
            reply_markup=cohort_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    type_name = data.get("type_name", "")

    notion = get_notion_service()
    if not notion:
        await state.clear()
        await message.answer(
            "Notion не настроен.", reply_markup=await back_to_menu_keyboard()
        )
        return

    try:
        success = await notion.add_option(type_name, name)
    except Exception:
        logger.exception("Notion API error adding option %s to %s", name, type_name)
        success = False
    finally:
        await notion.close()
        await state.clear()

    if success:
        await message.answer(
            f'Опция "<b>{e(name)}</b>" добавлена в <b>{e(type_name)}</b>.',
            reply_markup=await back_to_menu_keyboard(),
        )
    else:
        await message.answer(
            f'Не удалось добавить опцию "{e(name)}". Тип может быть нередактируемым.',
            reply_markup=await back_to_menu_keyboard(),
        )


# === Cancel FSM ===


@router.callback_query(F.data == "cohort_cancel_fsm")
async def cancel_fsm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await safe_edit_text(
        callback,
        "Действие отменено.",
        reply_markup=await back_to_menu_keyboard(),
    )
