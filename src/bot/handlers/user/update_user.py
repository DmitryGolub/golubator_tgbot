# app/bot/handlers/admin/update_user_fsm.py
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.bot.filters.permission import PermissionFilter
from src.bot.states.update_user import UpdateUserFSM
from src.bot.keyboards.user import (
    user_update_params_keyboard,
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
    CancelUpdateCB,
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


# ── Cancel handler (any state) ──────────────────────────────────────────────


@router.callback_query(CancelUpdateCB.filter())
async def cb_cancel_update(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await _msg(callback).edit_text(
        "Редактирование отменено.",
        reply_markup=await back_to_menu_keyboard(),
    )


# ── Step 1: Entry points → choosing_user ────────────────────────────────────


@router.callback_query(F.data == "user_update_menu")
async def cmd_start_update_user(callback: CallbackQuery, state: FSMContext):
    perms = await AuthService.get_user_permissions(callback.from_user.id)
    if not perms:
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    await callback.answer()
    users = await UserDAO.get_all()
    if not users:
        await _msg(callback).edit_text("Пользователи не найдены.")
        return

    await state.clear()
    await state.update_data(flow_perm="manage_users")
    await state.set_state(UpdateUserFSM.choosing_user)
    await _msg(callback).edit_text(
        "Выберите пользователя для редактирования:",
        reply_markup=users_keyboard(users),
    )


@router.callback_query(F.data == "mentor_update_student")
async def cmd_start_update_student_by_mentor(
    callback: CallbackQuery, state: FSMContext
):
    await callback.answer()
    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    if not mentees:
        await _msg(callback).edit_text(
            "Ученики не найдены.",
            reply_markup=await back_to_menu_keyboard(),
        )
        return

    await state.clear()
    await state.update_data(flow_perm="update_student_status")
    await state.set_state(UpdateUserFSM.choosing_user)
    await _msg(callback).edit_text(
        "Выберите ученика:",
        reply_markup=mentees_keyboard(mentees),
    )


# ── Step 2: User selected → viewing_user (show info + param buttons) ────────


async def _build_user_info(user_telegram_id: int) -> str:
    """Build user info text similar to list.py."""
    user = await UserDAO.find_one_or_none(telegram_id=user_telegram_id)
    if not user:
        return "Пользователь не найден."

    mentee = await MenteeDAO.find_by_telegram_id(user_telegram_id)
    mentor_name = "Отсутствует"
    mentor_username = ""
    if mentee and mentee.mentor:
        mentor_name = mentee.mentor.name or "Отсутствует"
        if mentee.mentor.user and mentee.mentor.user.username:
            mentor_username = f" @{e(mentee.mentor.user.username)}"

    role_display = user.role_rel.display_name if user.role_rel else "—"

    cohorts = await CohortDAO.get_user_cohorts(user_telegram_id)
    categories = [uc.cohort.value for uc in cohorts if uc.cohort.type == "Category"]
    cohort_display = ", ".join(categories) if categories else "Отсутствует"

    statuses = [uc.cohort.value for uc in cohorts if uc.cohort.type == "Status"]
    state_line = ""
    if statuses:
        state_line = f"   • Состояние: <b>{e(', '.join(statuses))}</b>\n"

    username_display = f" @{e(user.username)}" if user.username else ""

    return (
        f"👤 <b>{e(user.name)}</b>{username_display}\n"
        f"   • Ментор: <b>{e(mentor_name)}</b>{e(mentor_username)}\n"
        f"   • Направления: <b>{e(cohort_display)}</b>\n"
        f"   • Роль: <b>{e(role_display)}</b>\n"
        f"{state_line}\n"
        f"Выберите, что хотите изменить:"
    )


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_user),
    ChooseUserCB.filter(),
)
async def cb_user_selected(
    callback: CallbackQuery,
    callback_data: ChooseUserCB,
    state: FSMContext,
):
    await callback.answer()

    user_id = callback_data.user_id
    data = await state.get_data()
    flow_perm = data.get("flow_perm", "manage_users")
    is_mentor_flow = flow_perm == "update_student_status"

    info_text = await _build_user_info(user_id)
    kb = await user_update_params_keyboard(user_id, is_mentor_flow)

    await state.update_data(target_user_id=user_id)
    await state.set_state(UpdateUserFSM.viewing_user)
    await _msg(callback).edit_text(info_text, reply_markup=kb)


@router.callback_query(
    StateFilter(UpdateUserFSM.choosing_user),
    ChooseMenteeCB.filter(),
)
async def cb_mentee_selected(
    callback: CallbackQuery,
    callback_data: ChooseMenteeCB,
    state: FSMContext,
):
    await callback.answer()

    mentee = await MenteeDAO.find_one_or_none(id=callback_data.mentee_id)
    if not mentee:
        await _msg(callback).edit_text("Ученик не найден.")
        await state.clear()
        return

    user_id = mentee.telegram_id
    if not user_id:
        await _msg(callback).edit_text(
            "У ученика не привязан Telegram-аккаунт.",
            reply_markup=await back_to_menu_keyboard(),
        )
        await state.clear()
        return

    data = await state.get_data()
    flow_perm = data.get("flow_perm", "manage_users")
    is_mentor_flow = flow_perm == "update_student_status"

    info_text = await _build_user_info(user_id)
    kb = await user_update_params_keyboard(user_id, is_mentor_flow)

    await state.update_data(target_user_id=user_id)
    await state.set_state(UpdateUserFSM.viewing_user)
    await _msg(callback).edit_text(info_text, reply_markup=kb)


# ── Step 2.5: Param selected in viewing_user ────────────────────────────────


@router.callback_query(
    StateFilter(UpdateUserFSM.viewing_user),
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
            "Выберите новую роль:",
            reply_markup=await roles_keyboard(),
        )

    elif param == UpdateParam.STATUS:
        await state.set_state(UpdateUserFSM.choosing_value)
        await _msg(callback).edit_text(
            "Выберите новый статус:",
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
            "Выберите ментора:",
            reply_markup=mentors_keyboard(mentors),
        )

    elif param == UpdateParam.COHORT:
        kb = await cohort_types_keyboard()
        await state.set_state(UpdateUserFSM.choosing_cohort_type)
        await _msg(callback).edit_text(
            "Выберите тип когорты:",
            reply_markup=kb,
        )


# ── Step 2.5b: Cohort type selected ─────────────────────────────────────────


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
        f"Тип когорты: <b>{e(cohort_type)}</b>.\n\nВыберите значение:",
        reply_markup=kb,
    )


# ── Step 3: Value selected → apply change ───────────────────────────────────


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

    data = await state.get_data()
    target_user_id = data["target_user_id"]
    param = callback_data.param
    value = callback_data.value
    flow_perm = data.get("flow_perm", "manage_users")

    user = await UserDAO.find_one_or_none(telegram_id=target_user_id)
    if not user:
        await _msg(callback).edit_text("Пользователь не найден.")
        await state.clear()
        return

    param_human = {
        UpdateParam.STATUS: "статус",
        UpdateParam.ROLE: "роль",
        UpdateParam.COHORT: "когорта",
    }.get(param, str(param))

    if param == UpdateParam.ROLE:
        role_obj = await RoleDAO.get_by_name(value)
        if role_obj:
            await UserDAO.update(telegram_id=target_user_id, role_id=role_obj.id)
            await AuthService.invalidate_user(target_user_id)
            await MentorDAO.touch_updated_at(target_user_id)
            value_human = role_obj.display_name
        else:
            value_human = value

    elif param == UpdateParam.STATUS:
        mentee = await MenteeDAO.find_by_telegram_id(target_user_id)

        if flow_perm == "update_student_status":
            mentor_record = await MentorDAO.find_by_telegram_id(callback.from_user.id)
            if not mentee or mentee.mentor_id != (
                mentor_record.id if mentor_record else None
            ):
                await _msg(callback).edit_text(
                    "Можно обновлять только своих учеников.",
                    reply_markup=await back_to_menu_keyboard(),
                )
                await state.clear()
                return

        value_human = value

        if mentee and mentee.telegram_id:
            old_val, new_val = await CohortDAO.update_user_cohort_by_type(
                mentee.telegram_id, "Status", value
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
            target_user_id, cohort_type, value
        )
        value_human = f"{cohort_type}: {value}"
        if old_val != new_val:
            from src.models.trigger import TriggerType
            from src.services.events.dispatcher import EventDispatcher

            await EventDispatcher.emit(
                TriggerType.cohort_changed,
                {
                    "user_telegram_id": target_user_id,
                    "cohort_type": cohort_type,
                    "old_value": old_val,
                    "new_value": new_val,
                },
            )

    else:
        value_human = value

    username_part = f" @{e(user.username)}" if user.username else ""
    await _msg(callback).edit_text(
        f"Пользователь {e(user.name)}{username_part}\n"
        f"{e(param_human.title())} обновлено на: {e(value_human)}",
        reply_markup=await back_to_menu_keyboard(),
    )
    await state.clear()


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

    data = await state.get_data()
    target_user_id = data["target_user_id"]
    mentor_id = callback_data.mentor_id

    user = await UserDAO.find_one_or_none(telegram_id=target_user_id)
    if not user:
        await _msg(callback).edit_text("Пользователь не найден.")
        await state.clear()
        return

    mentor_record = await MentorDAO.find_by_telegram_id(mentor_id)
    mentee = await MenteeDAO.find_by_telegram_id(target_user_id)

    if mentor_record and mentee:
        is_new_mentor = mentee.mentor_id != mentor_record.id
        await MenteeDAO.update(mentee.id, mentor_id=mentor_record.id)
        value_human = mentor_record.name or f"id={mentor_id}"

        cohort_tids = await CohortDAO.get_telegram_ids_in_cohort("Status", "Greetings")
        if target_user_id in cohort_tids:
            await schedule_onboarding_for_mentor(user, mentor_id)

        mentor_user = await UserDAO.find_one_or_none(telegram_id=mentor_id)
        if mentor_user and is_new_mentor:
            await notify_student_new_mentor(user, mentor_user)
    elif not mentor_record:
        value_human = f"Ментор id={mentor_id} не найден в таблице менторов"
    else:
        value_human = "Профиль менти не найден для пользователя"

    username_part = f" @{e(user.username)}" if user.username else ""
    await _msg(callback).edit_text(
        f"Пользователь {e(user.name)}{username_part}\n"
        f"Ментор обновлено на: {e(value_human)}",
        reply_markup=await back_to_menu_keyboard(),
    )
    await state.clear()


# ── Pagination handlers ─────────────────────────────────────────────────────


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
    users = await _load_users_by_filter(users_filter)
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


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _load_users_by_filter(users_filter: str) -> list:
    if users_filter == "students":
        return await UserDAO.get_all(role_name="student")
    return await UserDAO.get_all()
