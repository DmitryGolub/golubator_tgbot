from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.bot.filters.role import RoleFilter
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.dao.cohort import CohortDAO
from src.models.user import Role


router = Router(name="cohort-list")
router.callback_query.filter(RoleFilter([Role.admin]))


@router.callback_query(F.data == "cohort_list")
async def show_cohort_list(callback: CallbackQuery):
    await callback.answer()

    cohorts = await CohortDAO.get_all()

    if not cohorts:
        await callback.message.edit_text(
            "Список когорт пуст.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    lines = ["<b>Список когорт:</b>", ""]
    for cohort in cohorts:
        lines.append(f"• {cohort.name}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_menu_keyboard(),
    )

