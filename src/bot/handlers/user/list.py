from contextlib import suppress

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from src.bot.callbacks.pagination import PageNavCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.user import user_list_paginated_keyboard
from src.bot.utils import safe_edit_text
from src.utils.tz import MSK
from src.dao.cohort import CohortDAO
from src.dao.mentee import MenteeDAO
from src.dao.user import UserDAO
from src.bot.keyboards.utils import format_username_display
from src.utils.escape import e
from src.utils.roles import is_mentor

router = Router(name="user")
router.callback_query.filter(PermissionFilter("manage_users"))


async def _build_user_list_page(
    page: int = 0, search_query: str | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    page_users, total_pages = await UserDAO.get_paginated(
        page=page, search=search_query
    )

    if not page_users:
        return "<b>Список пользователей пуст.</b>", await user_list_paginated_keyboard(
            1, 0
        )

    page_tids = [u.telegram_id for u in page_users]
    page_mentees = await MenteeDAO.get_by_telegram_ids(page_tids)
    mentee_by_tid: dict[int, object] = {}
    for mentee in page_mentees:
        if mentee.telegram_id:
            mentee_by_tid[mentee.telegram_id] = mentee

    cohorts_map = await CohortDAO.get_cohorts_batch(page_tids)

    answer = "<b>Список пользователей:</b>\n\n"

    for user in page_users:
        mentee = mentee_by_tid.get(user.telegram_id)
        mentor_line = ""
        if not is_mentor(user):
            mentor_name = "Отсутствует"
            mentor_username = ""
            if mentee and mentee.mentor:
                mentor_name = mentee.mentor.name or "Отсутствует"
                mentor_username = format_username_display(
                    mentee.mentor.user.username if mentee.mentor.user else None,
                    prefix="@",
                )
            mentor_line = f"   • Ментор: <b>{e(mentor_name)}</b> {e(mentor_username)}\n"

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

        reg_date = (
            f"{user.registered_at.astimezone(MSK):%d.%m.%Y %H:%M}"
            if user.registered_at
            else "—"
        )

        username_display = format_username_display(user.username, prefix="@")

        answer += (
            f"👤 <b>{e(user.name)}</b> {username_display}\n"
            f"{mentor_line}"
            f"   • Направления: <b>{e(cohort_display)}</b>\n"
            f"   • Роль: <b>{e(role_display)}</b>\n"
            f"{state_line}"
            f"   • Дата регистрации: {reg_date}\n\n"
        )

    markup = await user_list_paginated_keyboard(
        total_pages, page, search_query=search_query
    )
    return answer, markup


@router.callback_query(F.data.in_({"user_list", "menu_users"}))
async def cb_user_list(callback: CallbackQuery):
    text, markup = await _build_user_list_page(page=0)
    await safe_edit_text(callback, text, reply_markup=markup)
    with suppress(TelegramBadRequest):
        await callback.answer()


@router.callback_query(
    PermissionFilter("manage_users"),
    PageNavCB.filter(F.menu == "user_list"),
)
async def cb_user_list_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    data = await state.get_data()
    search_query = (data.get("_pagination_search") or {}).get("user_list")
    text, markup = await _build_user_list_page(
        page=callback_data.page, search_query=search_query
    )
    await safe_edit_text(callback, text, reply_markup=markup)
    with suppress(TelegramBadRequest):
        await callback.answer()
