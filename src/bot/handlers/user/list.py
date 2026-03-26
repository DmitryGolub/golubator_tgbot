from aiogram import Router, F
from aiogram.types import CallbackQuery

from src.dao.user import UserDAO
from src.dao.mentee import MenteeDAO
from src.dao.cohort import CohortDAO
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.utils.escape import e
from src.utils.telegram import split_message

router = Router(name="user")
router.callback_query.filter(PermissionFilter("manage_users"))


@router.callback_query(F.data.in_({"user_list", "menu_users"}))
async def cb_user_list(callback: CallbackQuery):
    await callback.answer()

    all_users = await UserDAO.get_all()

    if not all_users:
        return await callback.message.edit_text("<b>Список пользователей пуст.</b>")

    # Load all mentee profiles for mentor/state info
    all_mentees = await MenteeDAO.get_all_with_details()
    mentee_by_tid: dict[int, object] = {}
    for mentee in all_mentees:
        if mentee.telegram_id:
            mentee_by_tid[mentee.telegram_id] = mentee

    # Batch load cohorts to avoid N+1
    mentee_ids = [m.id for m in all_mentees]
    cohorts_map = await CohortDAO.get_cohorts_batch(mentee_ids)

    answer = "<b>Список пользователей:</b>\n\n"

    for user in all_users:
        mentee = mentee_by_tid.get(user.telegram_id)
        mentor_name = "Отсутствует"
        mentor_username = ""
        if mentee and mentee.mentor:
            mentor_name = mentee.mentor.name or "Отсутствует"
            if mentee.mentor.user and mentee.mentor.user.username:
                mentor_username = f"@{mentee.mentor.user.username}"

        role_display = user.role_rel.display_name if user.role_rel else "—"

        cohorts = cohorts_map.get(mentee.id, []) if mentee else []
        categories = [c.cohort.value for c in cohorts if c.cohort.type == "Category"]
        cohort_display = ", ".join(categories) if categories else "Отсутствует"

        statuses = [c.cohort.value for c in cohorts if c.cohort.type == "Status"]
        state_line = ""
        if statuses:
            state_line = f"   • Состояние: <b>{e(', '.join(statuses))}</b>\n"

        reg_date = f"{user.registered_at:%d.%m.%Y %H:%M}" if user.registered_at else "—"

        answer += (
            f"👤 <b>{e(user.name)}</b> @{e(user.username)}\n"
            f"   • Ментор: <b>{e(mentor_name)}</b> {e(mentor_username)}\n"
            f"   • Направления: <b>{e(cohort_display)}</b>\n"
            f"   • Роль: <b>{e(role_display)}</b>\n"
            f"{state_line}"
            f"   • Дата регистрации: {reg_date}\n\n"
        )

    chunks = split_message(answer)
    # First chunk replaces the original message
    await callback.message.edit_text(
        chunks[0],
        reply_markup=await back_to_menu_keyboard() if len(chunks) == 1 else None,
    )
    # Remaining chunks as new messages
    for i, chunk in enumerate(chunks[1:], 1):
        markup = await back_to_menu_keyboard() if i == len(chunks) - 1 else None
        await callback.message.answer(chunk, reply_markup=markup)
