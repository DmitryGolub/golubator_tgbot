from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import menu_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.keyboards.cohort import cohort_types_keyboard
from src.services.auth import AuthService
from src.services.ui_text import UiTextService
from src.dao.user import UserDAO
from src.dao.mentee import MenteeDAO
from src.dao.mentor import MentorDAO
from src.dao.mentor_stats import MentorStatsDAO
from src.dao.cohort import CohortDAO

from src.bot.keyboards.meeting import mentor_meetings_keyboard
from src.dao.meeting import MeetingDAO
from src.services.call_flow import ActiveCallNotFoundError, CallFlowService
from src.utils.escape import e

router = Router(name="menu")


async def _ensure_user(tg_user):
    from src.bot.handlers.common.start import _ensure_user as _start_ensure_user

    return await _start_ensure_user(tg_user)


async def _render_menu(message_or_callback, permissions: set[str]):
    text = await UiTextService.get("menu.title")
    markup = await menu_keyboard(permissions)

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text=text, reply_markup=markup)
    else:
        try:
            await message_or_callback.message.edit_text(text=text, reply_markup=markup)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    permissions = await AuthService.get_user_permissions(message.from_user.id)
    if not permissions:
        await _ensure_user(message.from_user)
        await AuthService.invalidate_user(message.from_user.id)
        permissions = await AuthService.get_user_permissions(message.from_user.id)
    if not permissions:
        text = await UiTextService.get("menu.access_denied")
        await message.answer(text)
        return

    await _render_menu(message, permissions)


@router.callback_query(F.data == "back_to_menu")
async def cb_menu(callback: CallbackQuery):
    await callback.answer()

    permissions = await AuthService.get_user_permissions(callback.from_user.id)
    if not permissions:
        await _ensure_user(callback.from_user)
        await AuthService.invalidate_user(callback.from_user.id)
        permissions = await AuthService.get_user_permissions(callback.from_user.id)
    if not permissions:
        text = await UiTextService.get("menu.access_denied")
        await callback.message.edit_text(text)
        return

    await _render_menu(callback, permissions)


# ==== ADMIN ====
@router.callback_query(PermissionFilter("manage_cohorts"), F.data == "menu_cohorts")
async def cb_menu_cohorts(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    types_with_counts = await CohortDAO.get_types_with_value_counts()
    if not types_with_counts:
        text = await UiTextService.get("cohort.not_found")
        try:
            await callback.message.edit_text(
                text, reply_markup=await back_to_menu_keyboard()
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
        return

    header = await UiTextService.get("cohort.types.header")
    markup, types_map = cohort_types_keyboard(types_with_counts)
    await state.update_data(cohort_types_map=types_map)
    try:
        await callback.message.edit_text(header, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(PermissionFilter("manage_mailings"), F.data == "menu_mailings")
async def cb_menu_mailings(callback: CallbackQuery):
    await callback.answer()
    text = "Рассылки перенесены в систему триггеров. Используйте меню триггеров."
    try:
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


# ==== MENTOR ====


async def _mentor_students_menu_kb():
    texts = await UiTextService.get_many(
        [
            "menu.mentor_students.btn.update",
            "menu.back",
        ]
    )
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts["menu.mentor_students.btn.update"],
        callback_data="mentor_update_student",
    )
    kb.button(text=texts["menu.back"], callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


async def _finish_active_call_text(mentor_id: int) -> str:
    service = CallFlowService()
    try:
        result = await service.end_active_call(mentor_id=mentor_id)
    except ActiveCallNotFoundError:
        return await UiTextService.get("menu.no_active_call")

    return await UiTextService.get(
        "menu.call_ended.with_meeting",
        id=str(result.meeting.id),
        start=f"{result.meeting.scheduled_at:%d.%m.%Y %H:%M}"
        if result.meeting.scheduled_at
        else "—",
        end=f"{result.meeting.completed_at:%d.%m.%Y %H:%M}"
        if result.meeting.completed_at
        else "—",
    )


@router.callback_query(
    PermissionFilter("view_students"), F.data == "mentor_students_menu"
)
async def cb_mentor_students_menu(callback: CallbackQuery):
    await callback.answer()

    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    if not mentees:
        text = await UiTextService.get("menu.students.empty")
        try:
            await callback.message.edit_text(
                text,
                reply_markup=await _mentor_students_menu_kb(),
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
        return

    header = await UiTextService.get("menu.students.header")
    lines = [header, ""]
    mentee_tids = [m.telegram_id for m in mentees if m.telegram_id is not None]
    cohorts_map = await CohortDAO.get_cohorts_batch(mentee_tids)
    for mentee in mentees:
        display_name = mentee.doc_name or (mentee.user.name if mentee.user else "—")
        username = mentee.user.username if mentee.user else None
        username_display = f"@{e(username)}" if username else ""
        cohorts = cohorts_map.get(mentee.telegram_id, []) if mentee.telegram_id else []
        categories = [c.cohort.value for c in cohorts if c.cohort.type == "Category"]
        cohort_display = ", ".join(categories) if categories else "Отсутствует"
        statuses = [c.cohort.value for c in cohorts if c.cohort.type == "Status"]
        status_display = ", ".join(statuses) if statuses else "—"
        lines.append(
            f"👤 <b>{e(display_name)}</b> {username_display}\n"
            f"   • Направления: <b>{e(cohort_display)}</b>\n"
            f"   • Состояние: <b>{e(status_display)}</b>\n"
        )

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=await _mentor_students_menu_kb(),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(
    PermissionFilter("view_students"), F.data == "mentor_students_add"
)
async def cb_mentor_students_add(callback: CallbackQuery):
    await callback.answer()
    permissions = await AuthService.get_user_permissions(callback.from_user.id)
    await callback.message.edit_text(
        "Выберите ученика для изменения статуса.",
        reply_markup=await menu_keyboard(permissions),
    )


@router.callback_query(PermissionFilter("end_call"), F.data == "mentor_end_call")
async def cb_mentor_end_call(callback: CallbackQuery):
    await callback.answer()
    text = await _finish_active_call_text(callback.from_user.id)
    meetings = await MeetingDAO.get_for_user(callback.from_user.id)
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    from src.bot.handlers.meeting import _filter_visible_meetings

    visible = _filter_visible_meetings(
        meetings,
        callback.from_user.id,
        viewer_is_mentor=True,
        mentor_tg_ids=mentor_tg_ids,
    )
    await callback.message.edit_text(
        text, reply_markup=mentor_meetings_keyboard(visible, page=0)
    )


@router.message(PermissionFilter("end_call"), Command("end_call"))
async def cmd_end_call(message: Message):
    text = await _finish_active_call_text(message.from_user.id)
    meetings = await MeetingDAO.get_for_user(message.from_user.id)
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    from src.bot.handlers.meeting import _filter_visible_meetings

    visible = _filter_visible_meetings(
        meetings,
        message.from_user.id,
        viewer_is_mentor=True,
        mentor_tg_ids=mentor_tg_ids,
    )
    await message.answer(text, reply_markup=mentor_meetings_keyboard(visible, page=0))


@router.callback_query(PermissionFilter("view_own_info"), F.data == "mentor_me_info")
async def cb_mentor_me_info(callback: CallbackQuery):
    await callback.answer()

    mentor_id = callback.from_user.id
    mentor = await MentorDAO.find_by_telegram_id(mentor_id)
    if not mentor:
        text = await UiTextService.get("menu.not_found")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return

    stats = await MentorStatsDAO.get_stats(mentor_id=mentor_id)

    title = await UiTextService.get("menu.me.title")
    lines = [
        f"{title}\n",
        f"Имя: <b>{e(mentor.name)}</b>",
        f"Юзернейм: @{e(mentor.user.username)}"
        if mentor.user and mentor.user.username
        else "",
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

    text = "\n".join(lines)

    try:
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


# ==== STUDENT ====
@router.callback_query(PermissionFilter("view_own_info"), F.data == "student_me_info")
async def cb_student_me_info(callback: CallbackQuery):
    await callback.answer()

    students = await UserDAO.get_all(telegram_id=callback.from_user.id)
    student = students[0] if students else None
    if not student:
        text = await UiTextService.get("menu.not_found")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return

    mentee = await MenteeDAO.find_by_telegram_id(callback.from_user.id)
    mentor_name = "Отсутствует"
    mentor_username = ""
    mentee_state = "—"
    if mentee:
        if mentee.mentor:
            mentor_name = mentee.mentor.name or "Отсутствует"
            if mentee.mentor.user and mentee.mentor.user.username:
                mentor_username = f"@{mentee.mentor.user.username}"
        cohorts = (
            await CohortDAO.get_user_cohorts(mentee.telegram_id)
            if mentee.telegram_id
            else []
        )
        statuses = [c.cohort.value for c in cohorts if c.cohort.type == "Status"]
        mentee_state = ", ".join(statuses) if statuses else "—"

    role_display = student.role_rel.display_name if student.role_rel else "—"

    title = await UiTextService.get("menu.me.title")
    text = (
        f"{title}\n\n"
        f"Имя: <b>{e(student.name)}</b>\n"
        f"Юзернейм: @{e(student.username)}\n"
        f"Роль: <b>{e(role_display)}</b>\n"
        f"Мой ментор: <b>{e(mentor_name)}</b> {e(mentor_username)}\n"
        f"Состояние: <b>{e(mentee_state)}</b>\n"
    )

    try:
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
