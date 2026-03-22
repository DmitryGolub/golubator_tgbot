# app/bot/handlers/admin/update_user_fsm.py
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from src.bot.filters.permission import PermissionFilter
from src.bot.states.update_user import UpdateUserFSM
from src.bot.keyboards.user import (
    update_param_keyboard,
    update_param_keyboard_for_mentor,
    roles_keyboard,
    statuses_keyboard,
    mentors_keyboard,
    users_keyboard,
)
from src.bot.callbacks.update_user import (
    ChooseParamCB,
    ChooseEnumValueCB,
    ChooseMentorCB,
    ChooseUserCB,
    UpdateParam,
)
from src.models.user import State
from src.dao.user import UserDAO
from src.dao.role import RoleDAO
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.services.auth import AuthService
from src.utils.onboarding import (
    schedule_onboarding_for_mentor,
    notify_student_new_mentor,
)
from src.utils.roles import is_student
from src.utils.escape import e

router = Router(name="update-user-fsm")
router.callback_query.filter(
    PermissionFilter(["manage_users", "update_student_status"])
)


def _msg(callback: CallbackQuery) -> Message:
    """Extract Message from callback, raising if inaccessible."""
    msg = callback.message
    if not isinstance(msg, Message):
        raise TypeError("Message is inaccessible")
    return msg


@router.callback_query(F.data == "user_update_menu")
async def cmd_start_update_user(callback: CallbackQuery, state: FSMContext):
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if not perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    keyboard = (
        update_param_keyboard()
        if "manage_users" in perms
        else update_param_keyboard_for_mentor()
    )

    await state.set_state(UpdateUserFSM.choosing_param)
    await _msg(callback).answer(
        "Что вы хотите обновить?",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "mentor_update_student")
async def cmd_start_update_student_by_mentor(
    callback: CallbackQuery, state: FSMContext
):
    await cmd_start_update_user(callback, state)


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_param),
    ChooseParamCB.filter(),
)
async def cb_choose_param(
    callback: CallbackQuery,
    callback_data: ChooseParamCB,
    state: FSMContext,
):
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if not perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        await state.clear()
        return

    if "manage_users" not in perms and callback_data.param != UpdateParam.STATUS:
        await _msg(callback).edit_text(
            "Ментору доступно только обновление статуса ученика.",
            reply_markup=await back_to_menu_keyboard(),
        )
        await state.clear()
        return

    await callback.answer()

    param = callback_data.param
    await state.update_data(param=param)

    if param == UpdateParam.ROLE:
        await state.set_state(UpdateUserFSM.choosing_value)
        await _msg(callback).edit_text(
            "Вы выбрали: обновить <b>роль</b>.\n\nТеперь выберите новую роль:",
            reply_markup=await roles_keyboard(),
        )

    elif param == UpdateParam.STATUS:
        await state.set_state(UpdateUserFSM.choosing_value)
        await _msg(callback).edit_text(
            "Вы выбрали: обновить <b>статус</b>.\n\nТеперь выберите новый статус:",
            reply_markup=statuses_keyboard(),
        )

    elif param == UpdateParam.MENTOR:
        mentors = await UserDAO.get_all(role_name="mentor")
        if not mentors:
            await _msg(callback).edit_text("Менторы не найдены.")
            await state.clear()
            return

        await state.set_state(UpdateUserFSM.choosing_value)
        await _msg(callback).edit_text(
            "Вы выбрали: обновить <b>ментора</b>.\n\nТеперь выберите ментора:",
            reply_markup=mentors_keyboard(mentors),
        )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_value),
    ChooseEnumValueCB.filter(),
)
async def cb_choose_enum_value(
    callback: CallbackQuery,
    callback_data: ChooseEnumValueCB,
    state: FSMContext,
):
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if not perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        await state.clear()
        return

    await callback.answer()

    param = callback_data.param  # ROLE or STATUS
    value = callback_data.value  # string value

    await state.update_data(
        chosen_value=value,
        chosen_value_type="enum",
    )

    users = (
        await UserDAO.get_all()
        if "manage_users" in perms
        else await UserDAO.get_all(mentor_id=callback.from_user.id)
    )
    if not users:
        await _msg(callback).edit_text("Пользователи не найдены.")
        await state.clear()
        return

    await state.set_state(UpdateUserFSM.choosing_user)

    human_param = "роль" if param == UpdateParam.ROLE else "статус"

    await _msg(callback).edit_text(
        f"Вы выбрали: обновить <b>{e(human_param)}</b> на <b>{e(value)}</b>.\n\n"
        f"Теперь выберите пользователя:",
        reply_markup=users_keyboard(users),
    )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_value),
    ChooseMentorCB.filter(),
)
async def cb_choose_mentor(
    callback: CallbackQuery,
    callback_data: ChooseMentorCB,
    state: FSMContext,
):
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if "manage_users" not in perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        await state.clear()
        return

    await callback.answer()

    mentor_id = callback_data.mentor_id
    await state.update_data(
        chosen_value=mentor_id,
        chosen_value_type="mentor",
    )

    students = await UserDAO.get_all(role_name="student")
    if not students:
        await _msg(callback).edit_text("Пользователи не найдены.")
        await state.clear()
        return

    await state.set_state(UpdateUserFSM.choosing_user)

    mentor = await UserDAO.find_one_or_none(telegram_id=mentor_id)
    mentor_text = mentor.name if mentor else f"id={mentor_id}"

    await _msg(callback).edit_text(
        f"Вы выбрали: обновить <b>ментора</b> на <b>{e(mentor_text)}</b>.\n\n"
        "Теперь выберите пользователя:",
        reply_markup=users_keyboard(students),
    )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_user),
    ChooseUserCB.filter(),
)
async def cb_choose_user_for_update(
    callback: CallbackQuery,
    callback_data: ChooseUserCB,
    state: FSMContext,
):
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if not perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        await state.clear()
        return

    await callback.answer()

    data = await state.get_data()
    param: UpdateParam = data["param"]
    chosen_value = data["chosen_value"]
    chosen_value_type = data["chosen_value_type"]

    user_id = callback_data.user_id
    user = await UserDAO.find_one_or_none(telegram_id=user_id)

    if not user:
        await _msg(callback).edit_text("Пользователь не найден.")
        await state.clear()
        return

    param_human = {
        UpdateParam.STATUS: "статус",
        UpdateParam.ROLE: "роль",
        UpdateParam.MENTOR: "ментор",
    }[param]

    if chosen_value_type == "enum":
        if param == UpdateParam.ROLE:
            role_obj = await RoleDAO.get_by_name(chosen_value)
            if role_obj:
                await UserDAO.update(telegram_id=user_id, role_id=role_obj.id)
                await AuthService.invalidate_user(user_id)
                value_human = role_obj.display_name
            else:
                value_human = chosen_value

        elif param == UpdateParam.STATUS:
            if "manage_users" not in perms and user.mentor_id != callback.from_user.id:
                await _msg(callback).edit_text(
                    "Можно обновлять только своих учеников.",
                    reply_markup=await back_to_menu_keyboard(),
                )
                await state.clear()
                return

            value_human = State[chosen_value].value

            await UserDAO.update(telegram_id=user_id, state=State[chosen_value])

        else:
            value_human = chosen_value

    elif chosen_value_type == "mentor":
        mentor = await UserDAO.find_one_or_none(telegram_id=chosen_value)
        is_new_mentor = user.mentor_id != chosen_value
        await UserDAO.update(telegram_id=user_id, mentor_id=chosen_value)

        value_human = mentor.name if mentor else f"id={chosen_value}"

        if is_student(user) and user.state == State.greeting and mentor:
            await schedule_onboarding_for_mentor(user, mentor.telegram_id)

        if mentor and is_new_mentor:
            await notify_student_new_mentor(user, mentor)

    else:
        value_human = str(chosen_value)

    await _msg(callback).edit_text(
        f"Пользователь {e(user.name)} @{e(user.username)}\n"
        f"{e(param_human.title())} обновлено на: {e(value_human)}",
        reply_markup=await back_to_menu_keyboard(),
    )
    await state.clear()
