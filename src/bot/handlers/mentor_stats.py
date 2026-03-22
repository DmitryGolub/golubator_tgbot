import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from src.bot.callbacks.mentor_stats import MentorStatsCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.mentor_stats import mentor_select_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.dao.mentor_stats import MentorStatsDAO
from src.dao.user import UserDAO
from src.services.ui_text import UiTextService
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="mentor_stats")


async def _format_stats(stats: dict, mentor_name: str) -> str:
    header = await UiTextService.get("mentor_stats.header", name=e(mentor_name))
    lines = [
        header,
        "",
        f"Созвоны: <b>{stats['total_calls']}</b>",
        f"Опросы заполнено: <b>{stats['total_surveys']}</b>",
    ]

    if stats.get("avg_mentor_style") is not None:
        lines.append(f"Средняя оценка стиля: <b>{stats['avg_mentor_style']}</b>")
    if stats.get("avg_knowledge_depth") is not None:
        lines.append(f"Средняя оценка знаний: <b>{stats['avg_knowledge_depth']}</b>")
    if stats.get("avg_understanding") is not None:
        lines.append(f"Средняя оценка понимания: <b>{stats['avg_understanding']}</b>")
    if stats.get("avg_satisfaction") is not None:
        lines.append(f"Общая удовлетворённость: <b>{stats['avg_satisfaction']}</b>")

    if all(
        stats.get(k) is None
        for k in ("avg_mentor_style", "avg_knowledge_depth", "avg_understanding")
    ):
        no_scores = await UiTextService.get("mentor_stats.no_scores")
        lines.append(f"\n{no_scores}")

    return "\n".join(lines)


# Mentor views own stats
@router.callback_query(PermissionFilter("view_own_info"), F.data == "mentor_my_stats")
async def cb_mentor_my_stats(callback: CallbackQuery):
    await callback.answer()

    mentor_id = callback.from_user.id
    mentors = await UserDAO.get_all(telegram_id=mentor_id)
    mentor = mentors[0] if mentors else None
    if not mentor:
        await callback.message.edit_text(
            await UiTextService.get("menu.not_found"),
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    stats = await MentorStatsDAO.get_stats(mentor_id=mentor_id)
    text = await _format_stats(stats, mentor.name)

    try:
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


# Admin: select mentor
@router.callback_query(PermissionFilter("manage_users"), F.data == "admin_mentor_stats")
async def cb_admin_mentor_stats(callback: CallbackQuery):
    await callback.answer()

    all_users = await UserDAO.get_all()
    mentors = [u for u in all_users if u.role_rel and u.role_rel.is_mentor]

    if not mentors:
        await callback.message.edit_text(
            await UiTextService.get("mentor_stats.no_mentors"),
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    try:
        await callback.message.edit_text(
            await UiTextService.get("mentor_stats.select"),
            reply_markup=mentor_select_keyboard(mentors),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


# Admin: view selected mentor stats
@router.callback_query(PermissionFilter("manage_users"), MentorStatsCB.filter())
async def cb_admin_view_mentor_stats(
    callback: CallbackQuery, callback_data: MentorStatsCB
):
    await callback.answer()

    mentor_id = callback_data.mentor_id
    mentors = await UserDAO.get_all(telegram_id=mentor_id)
    mentor = mentors[0] if mentors else None
    if not mentor:
        await callback.message.edit_text(
            await UiTextService.get("mentor_stats.not_found"),
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    stats = await MentorStatsDAO.get_stats(mentor_id=mentor_id)
    text = await _format_stats(stats, mentor.name)

    try:
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
