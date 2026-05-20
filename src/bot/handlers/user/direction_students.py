from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.keyboards.utils import format_username_display
from src.bot.utils import safe_edit_text
from src.dao.cohort import CohortDAO
from src.services.ui_text import UiTextService

router = Router(name="direction_students")
router.callback_query.filter(PermissionFilter("view_direction_students"))


@router.callback_query(F.data == "lead_direction_students")
async def cb_direction_students(callback: CallbackQuery):
    await callback.answer()

    grouped = await CohortDAO.get_students_for_direction_lead(callback.from_user.id)

    if not grouped:
        text = await UiTextService.get("direction.no_directions")
        kb = await back_to_menu_keyboard()
        await safe_edit_text(callback, text, reply_markup=kb)
        return

    lines: list[str] = []
    for direction, students in grouped.items():
        lines.append(f"<b>{direction}</b>")
        for i, (user, doc_name) in enumerate(students, 1):
            name = doc_name or user.name
            username_display = format_username_display(user.username, prefix=" @")
            lines.append(f"  {i}. {name}{username_display}")
        lines.append("")

    kb = await back_to_menu_keyboard()
    await safe_edit_text(callback, "\n".join(lines).strip(), reply_markup=kb)
