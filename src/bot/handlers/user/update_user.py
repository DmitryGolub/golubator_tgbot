# app/bot/handlers/admin/update_user_fsm.py
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery
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
    mentees_keyboard,
    cohort_types_keyboard,
    cohort_values_keyboard,
)
from src.bot.callbacks.update_user import (
    ChooseParamCB,
    ChooseEnumValueCB,
    ChooseMentorCB,
    ChooseMenteeCB,
    ChooseUserCB,
    ChooseCohortTypeCB,
    UpdateParam,
)
from src.bot.callbacks.pagination import PageNavCB
from src.dao.user import UserDAO
from src.dao.role import RoleDAO
from src.dao.mentor import MentorDAO
from src.dao.mentee import MenteeDAO
from src.dao.cohort import CohortDAO
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.services.auth import AuthService
from src.utils.onboarding import (
    schedule_onboarding_for_mentor,
    notify_student_new_mentor,
)
from src.utils.escape import e
from src.bot.utils import safe_message as _msg

router = Router(name="update-user-fsm")
router.callback_query.filter(
    PermissionFilter(["manage_users", "update_student_status"])
)


@router.callback_query(F.data == "user_update_menu")
async def cmd_start_update_user(callback: CallbackQuery, state: FSMContext):
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if not perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    data = await state.get_data()
    flow_perm = data.get("flow_perm", "manage_users")
    keyboard = (
        update_param_keyboard()
        if flow_perm == "manage_users"
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
    await callback.answer()
    await state.update_data(flow_perm="update_student_status", param=UpdateParam.STATUS)
    await state.set_state(UpdateUserFSM.choosing_value)
    await _msg(callback).answer(
        "Выберите новый статус:",
        reply_markup=await statuses_keyboard(),
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
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if not perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    flow_perm = data.get("flow_perm", "manage_users")

    if flow_perm != "manage_users" and callback_data.param != UpdateParam.STATUS:
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
            reply_markup=await statuses_keyboard(),
        )

    elif param == UpdateParam.MENTOR:
        mentors = await UserDAO.get_all_with_permission("manage_meetings")
        if not mentors:
            await _msg(callback).edit_text("Менторы не найдены.")
            await state.clear()
            return

        await state.set_state(UpdateUserFSM.choosing_value)
        await _msg(callback).edit_text(
            "Вы выбрали: обновить <b>ментора</b>.\n\nТеперь выберите ментора:",
            reply_markup=mentors_keyboard(mentors),
        )

    elif param == UpdateParam.COHORT:
        kb = await cohort_types_keyboard()
        await state.set_state(UpdateUserFSM.choosing_cohort_type)
        await _msg(callback).edit_text(
            "Вы выбрали: обновить <b>когорту</b>.\n\nВыберите тип когорты:",
            reply_markup=kb,
        )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_cohort_type),
    ChooseCohortTypeCB.filter(),
)
async def cb_choose_cohort_type(
    callback: CallbackQuery,
    callback_data: ChooseCohortTypeCB,
    state: FSMContext,
):
    await callback.answer()

    cohort_type = callback_data.cohort_type
    await state.update_data(cohort_type=cohort_type)

    kb = await cohort_values_keyboard(cohort_type)
    await state.set_state(UpdateUserFSM.choosing_value)
    await _msg(callback).edit_text(
        f"Тип когорты: <b>{e(cohort_type)}</b>.\n\nТеперь выберите значение:",
        reply_markup=kb,
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

    data = await state.get_data()
    flow_perm = data.get("flow_perm", "manage_users")

    human_param = {
        UpdateParam.ROLE: "роль",
        UpdateParam.STATUS: "статус",
        UpdateParam.COHORT: "когорта",
    }.get(param, str(param))

    if flow_perm == "update_student_status":
        mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
        if not mentees:
            await _msg(callback).edit_text("Пользователи не найдены.")
            await state.clear()
            return

        await state.set_state(UpdateUserFSM.choosing_user)
        await state.update_data(users_filter="mentor_mentees")

        await _msg(callback).edit_text(
            f"Вы выбрали: обновить <b>{e(human_param)}</b> на <b>{e(value)}</b>.\n\n"
            f"Теперь выберите ученика:",
            reply_markup=mentees_keyboard(mentees),
        )
        return

    users = await UserDAO.get_all()
    if not users:
        await _msg(callback).edit_text("Пользователи не найдены.")
        await state.clear()
        return

    await state.set_state(UpdateUserFSM.choosing_user)
    await state.update_data(users_filter="all")

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
    await state.update_data(users_filter="students")

    mentor_user = await UserDAO.find_one_or_none(telegram_id=mentor_id)
    mentor_text = mentor_user.name if mentor_user else f"id={mentor_id}"

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
        UpdateParam.COHORT: "когорта",
    }[param]

    if chosen_value_type == "enum":
        if param == UpdateParam.ROLE:
            role_obj = await RoleDAO.get_by_name(chosen_value)
            if role_obj:
                await UserDAO.update(telegram_id=user_id, role_id=role_obj.id)
                await AuthService.invalidate_user(user_id)
                await MentorDAO.touch_updated_at(user_id)
                value_human = role_obj.display_name
            else:
                value_human = chosen_value

        elif param == UpdateParam.STATUS:
            mentee = await MenteeDAO.find_by_telegram_id(user_id)

            if data.get("flow_perm") == "update_student_status":
                mentor_record = await MentorDAO.find_by_telegram_id(
                    callback.from_user.id
                )
                if not mentee or mentee.mentor_id != (
                    mentor_record.id if mentor_record else None
                ):
                    await _msg(callback).edit_text(
                        "Можно обновлять только своих учеников.",
                        reply_markup=await back_to_menu_keyboard(),
                    )
                    await state.clear()
                    return

            value_human = chosen_value

            if mentee and mentee.telegram_id:
                old_val, new_val = await CohortDAO.update_user_cohort_by_type(
                    mentee.telegram_id, "Status", chosen_value
                )
                if old_val != new_val:
                    from src.models.trigger import TriggerType
                    from src.services.events.dispatcher import EventDispatcher

                    await EventDispatcher.emit(
                        TriggerType.cohort_changed,
                        {
                            "user_telegram_id": mentee.telegram_id,
                            "cohort_type": "Status",
                            "old_value": old_val,
                            "new_value": new_val,
                        },
                    )
            else:
                value_human = f"{value_human} (профиль менти не найден)"

        elif param == UpdateParam.COHORT:
            cohort_type = data.get("cohort_type", "")
            old_val, new_val = await CohortDAO.update_user_cohort_by_type(
                user_id, cohort_type, chosen_value
            )
            value_human = f"{cohort_type}: {chosen_value}"
            if old_val != new_val:
                from src.models.trigger import TriggerType
                from src.services.events.dispatcher import EventDispatcher

                await EventDispatcher.emit(
                    TriggerType.cohort_changed,
                    {
                        "user_telegram_id": user_id,
                        "cohort_type": cohort_type,
                        "old_value": old_val,
                        "new_value": new_val,
                    },
                )

        else:
            value_human = chosen_value

    elif chosen_value_type == "mentor":
        mentor_record = await MentorDAO.find_by_telegram_id(chosen_value)
        mentee = await MenteeDAO.find_by_telegram_id(user_id)

        if mentor_record and mentee:
            is_new_mentor = mentee.mentor_id != mentor_record.id
            await MenteeDAO.update(mentee.id, mentor_id=mentor_record.id)
            value_human = mentor_record.name or f"id={chosen_value}"

            if mentee:
                # Check if mentee is in "Greetings" status cohort
                cohort_tids = await CohortDAO.get_telegram_ids_in_cohort(
                    "Status", "Greetings"
                )
                if user_id in cohort_tids:
                    await schedule_onboarding_for_mentor(user, chosen_value)

            mentor_user = await UserDAO.find_one_or_none(telegram_id=chosen_value)
            if mentor_user and is_new_mentor:
                await notify_student_new_mentor(user, mentor_user)
        elif not mentor_record:
            value_human = f"Ментор id={chosen_value} не найден в таблице менторов"
        else:
            value_human = "Профиль менти не найден для пользователя"

    else:
        value_human = str(chosen_value)

    username_part = f" @{e(user.username)}" if user.username else ""
    await _msg(callback).edit_text(
        f"Пользователь {e(user.name)}{username_part}\n"
        f"{e(param_human.title())} обновлено на: {e(value_human)}",
        reply_markup=await back_to_menu_keyboard(),
    )
    await state.clear()


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_user),
    ChooseMenteeCB.filter(),
)
async def cb_choose_mentee_for_update(
    callback: CallbackQuery,
    callback_data: ChooseMenteeCB,
    state: FSMContext,
):
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if not perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        await state.clear()
        return

    await callback.answer()

    data = await state.get_data()
    chosen_value = data["chosen_value"]

    mentee = await MenteeDAO.find_one_or_none(id=callback_data.mentee_id)
    if not mentee:
        await _msg(callback).edit_text("Ученик не найден.")
        await state.clear()
        return

    if data.get("flow_perm") == "update_student_status":
        mentor_record = await MentorDAO.find_by_telegram_id(callback.from_user.id)
        if mentee.mentor_id != (mentor_record.id if mentor_record else None):
            await _msg(callback).edit_text(
                "Можно обновлять только своих учеников.",
                reply_markup=await back_to_menu_keyboard(),
            )
            await state.clear()
            return

    if not mentee.telegram_id:
        await _msg(callback).edit_text(
            "У ученика не привязан Telegram-аккаунт.",
            reply_markup=await back_to_menu_keyboard(),
        )
        await state.clear()
        return

    old_val, new_val = await CohortDAO.update_user_cohort_by_type(
        mentee.telegram_id, "Status", chosen_value
    )
    if old_val != new_val:
        from src.models.trigger import TriggerType
        from src.services.events.dispatcher import EventDispatcher

        await EventDispatcher.emit(
            TriggerType.cohort_changed,
            {
                "user_telegram_id": mentee.telegram_id,
                "cohort_type": "Status",
                "old_value": old_val,
                "new_value": new_val,
            },
        )

    display_name = mentee.doc_name or mentee.name or f"id={mentee.id}"
    username = ""
    if mentee.user and mentee.user.username:
        username = f" @{e(mentee.user.username)}"

    await _msg(callback).edit_text(
        f"Ученик {e(display_name)}{username}\nСтатус обновлено на: {e(chosen_value)}",
        reply_markup=await back_to_menu_keyboard(),
    )
    await state.clear()


async def _load_users_by_filter(users_filter: str, caller_id: int) -> list:
    if users_filter == "students":
        return await UserDAO.get_all(role_name="student")
    return await UserDAO.get_all()


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_user),
    PageNavCB.filter(F.menu == "users"),
)
async def cb_users_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    data = await state.get_data()
    users_filter = data.get("users_filter", "all")
    users = await _load_users_by_filter(users_filter, callback.from_user.id)
    await _msg(callback).edit_reply_markup(
        reply_markup=users_keyboard(users, page=callback_data.page)
    )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_user),
    PageNavCB.filter(F.menu == "mentees"),
)
async def cb_mentees_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    await _msg(callback).edit_reply_markup(
        reply_markup=mentees_keyboard(mentees, page=callback_data.page)
    )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_value),
    PageNavCB.filter(F.menu == "mentors"),
)
async def cb_mentors_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    mentors = await UserDAO.get_all_with_permission("manage_meetings")
    await _msg(callback).edit_reply_markup(
        reply_markup=mentors_keyboard(mentors, page=callback_data.page)
    )
