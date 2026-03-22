from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.bot.callbacks.cohort import CohortTypeCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.cohort import (
    cohort_type_detail_keyboard,
    cohort_types_keyboard,
    cohort_options_select_keyboard,
)
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.core.config import settings
from src.services.notion_client import NotionService


router = Router(name="cohort-list")
router.callback_query.filter(PermissionFilter("manage_cohorts"))


def _get_notion() -> NotionService | None:
    if not settings.NOTION_TOKEN or not settings.NOTION_DATABASE_ID:
        return None
    return NotionService(settings.NOTION_TOKEN, settings.NOTION_DATABASE_ID)


@router.callback_query(F.data == "cohort_list")
async def show_cohort_types(callback: CallbackQuery):
    await callback.answer()

    notion = _get_notion()
    if not notion:
        await callback.message.edit_text(
            "Notion не настроен (NOTION_TOKEN / NOTION_DATABASE_ID).",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    try:
        types = await notion.get_cohort_types()
    finally:
        await notion.close()

    if not types:
        await callback.message.edit_text(
            "Типы когорт не найдены в Notion.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        "<b>Типы когорт:</b>",
        reply_markup=cohort_types_keyboard(types),
    )


@router.callback_query(CohortTypeCB.filter())
async def show_cohort_type_detail(
    callback: CallbackQuery, callback_data: CohortTypeCB
):
    await callback.answer()

    notion = _get_notion()
    if not notion:
        return

    try:
        types = await notion.get_cohort_types()
    finally:
        await notion.close()

    info = next((t for t in types if t.name == callback_data.name), None)
    if not info:
        await callback.message.edit_text(
            f'Тип "{callback_data.name}" не найден.',
            reply_markup=back_to_menu_keyboard(),
        )
        return

    options_text = "\n".join(f"  • {o}" for o in info.options) if info.options else "  (пусто)"
    text = (
        f"<b>{info.name}</b> ({info.notion_type})\n\n"
        f"Опции:\n{options_text}\n\n"
        f"{'✏️ Редактируемые опции' if info.editable else '🔒 Опции не редактируются через API'}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=cohort_type_detail_keyboard(info),
    )


@router.callback_query(F.data.startswith("cohort_rename_opt_list:"))
async def show_rename_options_list(callback: CallbackQuery):
    await callback.answer()
    type_name = callback.data.split(":", 1)[1]

    notion = _get_notion()
    if not notion:
        return

    try:
        options = await notion.get_options(type_name)
    finally:
        await notion.close()

    if not options:
        await callback.message.edit_text(
            "Нет опций для переименования.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        f"Выберите опцию для переименования в <b>{type_name}</b>:",
        reply_markup=cohort_options_select_keyboard(type_name, options, "rename"),
    )


@router.callback_query(F.data.startswith("cohort_delete_opt_list:"))
async def show_delete_options_list(callback: CallbackQuery):
    await callback.answer()
    type_name = callback.data.split(":", 1)[1]

    notion = _get_notion()
    if not notion:
        return

    try:
        options = await notion.get_options(type_name)
    finally:
        await notion.close()

    if not options:
        await callback.message.edit_text(
            "Нет опций для удаления.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        f"Выберите опцию для удаления в <b>{type_name}</b>:",
        reply_markup=cohort_options_select_keyboard(type_name, options, "delete"),
    )
