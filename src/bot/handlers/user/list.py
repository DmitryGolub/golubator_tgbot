from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from src.bot.callbacks.pagination import PageNavCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.pagination import get_page_slice
from src.bot.keyboards.user import user_list_paginated_keyboard
from src.dao.cohort import CohortDAO
from src.dao.mentee import MenteeDAO
from src.dao.user import UserDAO
from src.utils.escape import e

router = Router(name="user")
router.callback_query.filter(PermissionFilter("manage_users"))


async def _build_user_list_page(page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    # TODO: SQL-level pagination (LIMIT/OFFSET) when user count exceeds ~500
    all_users = await UserDAO.get_all()

    if not all_users:
        return "<b>Список пользователей пуст.</b>", await user_list_paginated_keyboard(
            1, 0
        )

    all_mentees = await MenteeDAO.get_all_with_details()
    mentee_by_tid: dict[int, object] = {}
    for mentee in all_mentees:
        if mentee.telegram_id:
            mentee_by_tid[mentee.telegram_id] = mentee

    mentee_tids = [m.telegram_id for m in all_mentees if m.telegram_id is not None]
    cohorts_map = await CohortDAO.get_cohorts_batch(mentee_tids)

    page_users, total_pages = get_page_slice(all_users, page)

    answer = "<b>Список пользователей:</b>\n\n"

    for user in page_users:
        mentee = mentee_by_tid.get(user.telegram_id)
        mentor_name = "Отсутствует"
        mentor_username = ""
        if mentee and mentee.mentor:
            mentor_name = mentee.mentor.name or "Отсутствует"
            if mentee.mentor.user and mentee.mentor.user.username:
                mentor_username = f"@{mentee.mentor.user.username}"

        role_display = user.role_rel.display_name if user.role_rel else "—"

        cohorts = (
            cohorts_map.get(mentee.telegram_id, [])
            if mentee and mentee.telegram_id
            else []
        )
        categories = [c.cohort.value for c in cohorts if c.cohort.type == "Category"]
        cohort_display = ", ".join(categories) if categories else "Отсутствует"

        statuses = [c.cohort.value for c in cohorts if c.cohort.type == "Status"]
        state_line = ""
        if statuses:
            state_line = f"   • Состояние: <b>{e(', '.join(statuses))}</b>\n"

        reg_date = f"{user.registered_at:%d.%m.%Y %H:%M}" if user.registered_at else "—"

        placeholder_badge = " [Нет Telegram]" if user.is_placeholder else ""
        username_display = f"@{e(user.username)}" if user.username else ""

        answer += (
            f"👤 <b>{e(user.name)}</b> {username_display}{placeholder_badge}\n"
            f"   • Ментор: <b>{e(mentor_name)}</b> {e(mentor_username)}\n"
            f"   • Направления: <b>{e(cohort_display)}</b>\n"
            f"   • Роль: <b>{e(role_display)}</b>\n"
            f"{state_line}"
            f"   • Дата регистрации: {reg_date}\n\n"
        )

    markup = await user_list_paginated_keyboard(total_pages, page)
    return answer, markup


@router.callback_query(F.data.in_({"user_list", "menu_users"}))
async def cb_user_list(callback: CallbackQuery):
    await callback.answer()
    text, markup = await _build_user_list_page(page=0)
    await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(
    PermissionFilter("manage_users"),
    PageNavCB.filter(F.menu == "user_list"),
)
async def cb_user_list_page(callback: CallbackQuery, callback_data: PageNavCB):
    await callback.answer()
    text, markup = await _build_user_list_page(page=callback_data.page)
    await callback.message.edit_text(text, reply_markup=markup)
