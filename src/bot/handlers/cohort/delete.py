from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.bot.callbacks.cohort import DeleteCohortTypeCB, DeleteOptionCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.cohort import cohort_confirm_delete_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.services.notion_client import get_notion_service
from src.utils.escape import e


router = Router(name="cohort-delete")
router.callback_query.filter(PermissionFilter("manage_cohorts"))


# === Delete cohort type (show confirmation) ===

@router.callback_query(DeleteCohortTypeCB.filter())
async def confirm_delete_type(
    callback: CallbackQuery, callback_data: DeleteCohortTypeCB
):
    await callback.answer()
    await callback.message.edit_text(
        f'Вы уверены, что хотите удалить тип когорты "<b>{e(callback_data.name)}</b>"?\n'
        f"Это удалит свойство и данные у всех страниц в Notion!",
        reply_markup=cohort_confirm_delete_keyboard(callback_data.name),
    )


@router.callback_query(F.data.startswith("cohort_confirm_del_type:"))
async def do_delete_type(callback: CallbackQuery):
    await callback.answer()
    type_name = callback.data.split(":", 1)[1]

    notion = get_notion_service()
    if not notion:
        await callback.message.edit_text(
            "Notion не настроен.", reply_markup=back_to_menu_keyboard()
        )
        return

    try:
        success = await notion.delete_cohort_type(type_name)
    finally:
        await notion.close()

    if success:
        await callback.message.edit_text(
            f'Тип когорты "<b>{e(type_name)}</b>" удалён из Notion.',
            reply_markup=back_to_menu_keyboard(),
        )
    else:
        await callback.message.edit_text(
            f'Не удалось удалить тип "{e(type_name)}". Возможно, он защищён.',
            reply_markup=back_to_menu_keyboard(),
        )


# === Delete option ===

@router.callback_query(DeleteOptionCB.filter())
async def delete_option(
    callback: CallbackQuery, callback_data: DeleteOptionCB
):
    await callback.answer()

    notion = get_notion_service()
    if not notion:
        await callback.message.edit_text(
            "Notion не настроен.", reply_markup=back_to_menu_keyboard()
        )
        return

    try:
        success = await notion.remove_option(
            callback_data.type_name, callback_data.option_name
        )
    finally:
        await notion.close()

    if success:
        await callback.message.edit_text(
            f'Опция "<b>{e(callback_data.option_name)}</b>" удалена из <b>{e(callback_data.type_name)}</b>.',
            reply_markup=back_to_menu_keyboard(),
        )
    else:
        await callback.message.edit_text(
            f'Не удалось удалить опцию "{e(callback_data.option_name)}".',
            reply_markup=back_to_menu_keyboard(),
        )
