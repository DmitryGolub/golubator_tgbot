from aiogram import Router, F
from aiogram.types import CallbackQuery

from src.dao.user import UserDAO

from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.keyboards.user import user_update_menu, users_for_action_keyboard

from src.bot.callback.user import UserActionSelectCB, UserAction, UserActionUserCB


router = Router(name="user")


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

        answer += (
            f"👤 <b>{user.name}</b> @{user.username}\n"
            f"   • Ментор: <b>{mentor_name}</b> {mentor_username}\n"
            f"   • Роль: <b>{user.role.value}</b>\n"
            f"   • Состояние: <b>{user.state.value}</b>\n"
            f"   • Дата регистрации: {user.registered_at:%d.%m.%Y %H:%M}\n\n"
        )

    return await callback.message.edit_text(answer, reply_markup=back_to_menu_keyboard())


@router.callback_query(F.data == "user_update_menu")
async def cb_user_list(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text("Выберите действие над пользователем", reply_markup=user_update_menu())


@router.callback_query(UserActionSelectCB.filter())
async def cb_user_action_select(callback: CallbackQuery, callback_data: UserActionSelectCB):
    await callback.answer()

    action = callback_data.action

    users = await UserDAO.get_all()
    if not users:
        await callback.message.edit_text("Пользователей пока нет.")
        return

    # Текст в зависимости от действия (чисто для красоты)
    action_text_map = {
        "view": "просмотра информации о пользователе",
        "edit": "редактирования пользователя",
        "delete": "удаления пользователя",
    }
    action_text = action_text_map.get(action.value, "действия с пользователем")

    await callback.message.edit_text(
        text=f"Выбрано действие: <b>{action_text}</b>.\n"
             f"Теперь выбери пользователя:",
        reply_markup=users_for_action_keyboard(users, action),
    )


@router.callback_query(UserActionUserCB.filter())
async def cb_user_action_user(callback: CallbackQuery, callback_data: UserActionUserCB):
    await callback.answer()

    action: UserAction = callback_data.action
    user_id: int = callback_data.user_id

    user = await UserDAO.find_one_or_none(telegram_id=user_id)
    if not user:
        await callback.message.answer("Пользователь не найден.")
        return

    action_human = {
        UserAction.update_role: "обновить роль",
        UserAction.update_state: "обновить состояние",
        UserAction.update_mentor: "обновить ментора",
    }.get(action, "совершить действие с пользователем")

    user_display = f"{user.name} (@{user.username})" if user.username else user.name

    await callback.message.answer(
        f"Ты выбрал: <b>{action_human}</b>\n"
        f"Цель: <b>{user_display}</b>"
    )
