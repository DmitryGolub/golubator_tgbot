from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.bot.callbacks.cohort import DeleteCohortCB
from src.bot.filters.role import RoleFilter
from src.bot.keyboards.cohort import cohort_delete_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.dao.cohort import CohortDAO
from src.models.user import Role


router = Router(name="cohort-delete")
router.callback_query.filter(RoleFilter([Role.admin]))


@router.callback_query(F.data == "cohort_delete")
async def start_delete_cohort(callback: CallbackQuery):
    await callback.answer()

    cohorts = await CohortDAO.get_all()

    if not cohorts:
        await callback.message.edit_text(
            "Список когорт пуст.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        "Выберите когорту для удаления:",
        reply_markup=cohort_delete_keyboard(cohorts),
    )


@router.callback_query(DeleteCohortCB.filter())
async def delete_cohort(callback: CallbackQuery, callback_data: DeleteCohortCB):
    await callback.answer()

    cohort = await CohortDAO.find_one_or_none(id=callback_data.cohort_id)

    if not cohort:
        await callback.message.edit_text(
            "Когорта не найдена.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await CohortDAO.delete(id=cohort.id)

    await callback.message.edit_text(
        f'Когорта "{cohort.name}" удалена.',
        reply_markup=back_to_menu_keyboard(),
    )

