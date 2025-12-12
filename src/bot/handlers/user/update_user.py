# app/bot/handlers/admin/update_user_fsm.py
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.bot.states.update_user import UpdateUserFSM
from src.bot.keyboards.user import (
    update_param_keyboard,
    roles_keyboard,
    statuses_keyboard,
    mentors_keyboard,
    cohorts_keyboard,
    users_keyboard,
)
from src.bot.callbacks.update_user import (
    ChooseParamCB,
    ChooseEnumValueCB,
    ChooseMentorCB,
    ChooseCohortCB,
    ChooseUserCB,
    UpdateParam,
)
from src.models.user import Role, State
from src.dao.user import UserDAO
from src.dao.cohort import CohortDAO
from src.bot.keyboards.menu import back_to_menu_keyboard

router = Router(name="update-user-fsm")


@router.callback_query(F.data == "user_update_menu")
async def cmd_start_update_user(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UpdateUserFSM.choosing_param)
    await callback.message.answer(
        "Что вы хотите обновить?",
        reply_markup=update_param_keyboard(),
    )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_param),
    ChooseParamCB.filter(),
)
async def cb_choose_param(
    callback: CallbackQuery,
    callback_data: ChooseParamCB,
    state: FSMContext,
):
    await callback.answer()

    param = callback_data.param
    await state.update_data(param=param)

    if param == UpdateParam.ROLE:
        await state.set_state(UpdateUserFSM.choosing_value)
        await callback.message.edit_text(
            "Вы выбрали: обновить <b>роль</b>.\n\n"
            "Теперь выберите новую роль:",
            reply_markup=roles_keyboard(),
        )

    elif param == UpdateParam.STATUS:
        await state.set_state(UpdateUserFSM.choosing_value)
        await callback.message.edit_text(
            "Вы выбрали: обновить <b>статус</b>.\n\n"
            "Теперь выберите новый статус:",
            reply_markup=statuses_keyboard(),
        )

    elif param == UpdateParam.MENTOR:
        mentors = await UserDAO.get_all(role=Role.mentor)
        if not mentors:
            await callback.message.edit_text("Менторы не найдены.")
            await state.clear()
            return

        await state.set_state(UpdateUserFSM.choosing_value)
        await callback.message.edit_text(
            "Вы выбрали: обновить <b>ментора</b>.\n\n"
            "Теперь выберите ментора:",
            reply_markup=mentors_keyboard(mentors),
        )

    elif param == UpdateParam.COHORT:
        cohorts = await CohortDAO.get_all()
        if not cohorts:
            await callback.message.edit_text("Когорты не найдены.")
            await state.clear()
            return

        await state.set_state(UpdateUserFSM.choosing_value)
        await callback.message.edit_text(
            "Вы выбрали: обновить <b>когорту</b>.\n\n"
            "Теперь выберите когорту:",
            reply_markup=cohorts_keyboard(cohorts),
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
    await callback.answer()

    param = callback_data.param      # ROLE или STATUS
    value = callback_data.value      # строка value enum'а

    await state.update_data(
        chosen_value=value,
        chosen_value_type="enum",
    )

    users = await UserDAO.get_all()
    if not users:
        await callback.message.edit_text("Пользователи не найдены.")
        await state.clear()
        return

    await state.set_state(UpdateUserFSM.choosing_user)

    human_param = "роль" if param == UpdateParam.ROLE else "статус"

    await callback.message.edit_text(
        f"Вы выбрали: обновить <b>{human_param}</b> на <b>{value}</b>.\n\n"
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
    await callback.answer()

    mentor_id = callback_data.mentor_id
    await state.update_data(
        chosen_value=mentor_id,
        chosen_value_type="mentor",
    )

    students = await UserDAO.get_all(role=Role.student)
    if not students:
        await callback.message.edit_text("Пользователи не найдены.")
        await state.clear()
        return

    await state.set_state(UpdateUserFSM.choosing_user)

    # Можно дополнительно подтянуть имя ментора для текста
    mentor = await UserDAO.find_one_or_none(telegram_id=mentor_id)
    mentor_text = mentor.name if mentor else f"id={mentor_id}"

    await callback.message.edit_text(
        f"Вы выбрали: обновить <b>ментора</b> на <b>{mentor_text}</b>.\n\n"
        "Теперь выберите пользователя:",
        reply_markup=users_keyboard(students),
    )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_value),
    ChooseCohortCB.filter(),
)
async def cb_choose_cohort(
    callback: CallbackQuery,
    callback_data: ChooseCohortCB,
    state: FSMContext,
):
    await callback.answer()

    cohort_id = callback_data.cohort_id
    await state.update_data(
        chosen_value=cohort_id,
        chosen_value_type="cohort",
    )

    users = await UserDAO.get_all()
    if not users:
        await callback.message.edit_text("Пользователи не найдены.")
        await state.clear()
        return

    await state.set_state(UpdateUserFSM.choosing_user)

    cohort = await CohortDAO.find_one_or_none(id=cohort_id)
    cohort_text = cohort.name if cohort else f"id={cohort_id}"

    await callback.message.edit_text(
        f"Вы выбрали: обновить <b>когорту</b> на <b>{cohort_text}</b>.\n\n"
        "Теперь выберите пользователя:",
        reply_markup=users_keyboard(users),
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
    await callback.answer()

    data = await state.get_data()
    param: UpdateParam = data["param"]
    chosen_value = data["chosen_value"]
    chosen_value_type = data["chosen_value_type"]

    user_id = callback_data.user_id
    user = await UserDAO.find_one_or_none(telegram_id=user_id)

    if not user:
        await callback.message.edit_text("Пользователь не найден.")
        await state.clear()
        return

    # человекочитаемое название параметра
    param_human = {
        UpdateParam.STATUS: "статус",
        UpdateParam.ROLE: "роль",
        UpdateParam.MENTOR: "ментор",
        UpdateParam.COHORT: "когорта",
    }[param]

    # человекочитаемое значение
    if chosen_value_type == "enum":
        if param == UpdateParam.ROLE:
            value_human = Role[chosen_value].value

            await UserDAO.update(telegram_id=user_id, role=Role[chosen_value])

        elif param == UpdateParam.STATUS:
            value_human = State[chosen_value].value

            await UserDAO.update(telegram_id=user_id, state=State[chosen_value])

        else:
            value_human = chosen_value

    elif chosen_value_type == "mentor":

        mentor = await UserDAO.find_one_or_none(telegram_id=chosen_value)
        await UserDAO.update(telegram_id=user_id, mentor_id=chosen_value)

        value_human = mentor.name if mentor else f"id={chosen_value}"

    elif chosen_value_type == "cohort":

        cohort = await CohortDAO.find_one_or_none(id=chosen_value)
        await UserDAO.update(telegram_id=user_id, cohort_id=chosen_value)

        value_human = cohort.name if cohort else f"id={chosen_value}"

    else:
        value_human = str(chosen_value)

    await callback.message.edit_text(
        f"Пользователь {user.name} @{user.username}\n"
        f"{param_human.title()} обновлено на: {value_human}",
        reply_markup=back_to_menu_keyboard(),
    )
    await state.clear()
