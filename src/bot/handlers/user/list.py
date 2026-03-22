from aiogram import Router, F
from aiogram.types import CallbackQuery

from src.dao.user import UserDAO
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import back_to_menu_keyboard

router = Router(name="user")
router.callback_query.filter(PermissionFilter("manage_users"))


@router.callback_query(F.data == "user_list")
async def cb_user_list(callback: CallbackQuery):
    await callback.answer()

    all_users = await UserDAO.get_all()

    if not all_users:
        return await callback.message.edit_text("<b>Список пользователей пуст.</b>")

    answer = "<b>Список пользователей:</b>\n\n"

    for user in all_users:
        mentor_name = user.mentor.name if user.mentor else "Отсутствует"
        mentor_username = f"@{user.mentor.username}" if user.mentor else ""
        cohort_name = user.cohort.name if user.cohort else "Отсутствует"
        role_display = user.role_rel.display_name if user.role_rel else "—"

        answer += (
            f"👤 <b>{user.name}</b> @{user.username}\n"
            f"   • Ментор: <b>{mentor_name}</b> {mentor_username}\n"
            f"   • Когорта: <b>{cohort_name}</b>\n"
            f"   • Роль: <b>{role_display}</b>\n"
            f"   • Состояние: <b>{user.state.value}</b>\n"
            f"   • Дата регистрации: {user.registered_at:%d.%m.%Y %H:%M}\n\n"
        )

    return await callback.message.edit_text(answer, reply_markup=back_to_menu_keyboard())
