from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.bot.callbacks.cohort import CohortTypeCB, OptionListCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.cohort import (
    cohort_type_detail_keyboard,
    cohort_types_keyboard,
    cohort_options_select_keyboard,
)
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.services.notion_client import get_notion_service
from src.services.ui_text import UiTextService
from src.utils.escape import e


router = Router(name="cohort-list")
router.callback_query.filter(PermissionFilter("manage_cohorts"))


@router.callback_query(F.data == "cohort_list")
async def show_cohort_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    notion = get_notion_service()
    if not notion:
        text = await UiTextService.get("cohort.not_configured")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return

    loading = await UiTextService.get("common.loading")
    await callback.message.edit_text(loading)

    try:
        types = await notion.get_cohort_types()
    finally:
        await notion.close()

    if not types:
        text = await UiTextService.get("cohort.not_found")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return

    header = await UiTextService.get("cohort.types.header")
    markup, types_map = cohort_types_keyboard(types)
    await state.update_data(cohort_types_map=types_map)
    await callback.message.edit_text(header, reply_markup=markup)


@router.callback_query(CohortTypeCB.filter())
async def show_cohort_type_detail(
    callback: CallbackQuery, callback_data: CohortTypeCB, state: FSMContext
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
        return

    try:
        types = await notion.get_cohort_types()
    finally:
        await notion.close()

    info = next((t for t in types if t.name == type_name), None)
    if not info:
        await callback.message.edit_text(
            f'Тип "{e(type_name)}" не найден.',
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    await state.update_data(
        current_type_name=type_name, current_type_idx=callback_data.idx
    )

    options_text = (
        "\n".join(f"  • {e(o)}" for o in info.options) if info.options else "  (пусто)"
    )
    text = (
        f"<b>{e(info.name)}</b> ({e(info.notion_type)})\n\n"
        f"Опции:\n{options_text}\n\n"
        f"{'✏️ Редактируемые опции' if info.editable else '🔒 Опции не редактируются через API'}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=cohort_type_detail_keyboard(info, callback_data.idx),
    )


@router.callback_query(OptionListCB.filter())
async def show_options_list(
    callback: CallbackQuery, callback_data: OptionListCB, state: FSMContext
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
        return

    try:
        options = await notion.get_options(type_name)
    finally:
        await notion.close()

    action = callback_data.action
    action_label = "переименования" if action == "rename" else "удаления"

    if not options:
        await callback.message.edit_text(
            f"Нет опций для {action_label}.",
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    markup, options_map = cohort_options_select_keyboard(options, action)
    await state.update_data(
        cohort_options_map=options_map,
        current_type_name=type_name,
    )

    await callback.message.edit_text(
        f"Выберите опцию для {action_label} в <b>{e(type_name)}</b>:",
        reply_markup=markup,
    )
