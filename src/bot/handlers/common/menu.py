from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import menu_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.keyboards.cohort import cohort_actions_keyboard
from src.services.auth import AuthService
from src.services.ui_text import UiTextService
from src.dao.user import UserDAO
from src.dao.role import RoleDAO
from src.dao.mentee import MenteeDAO
from src.dao.cohort import CohortDAO

from src.core.config import settings
from src.services.call_flow import ActiveCallNotFoundError, CallFlowService
from src.utils.escape import e

router = Router(name="menu")


async def _auto_register(tg_user):
    """Register user if not exists, return User."""
    existing = await UserDAO.find_one_or_none(telegram_id=tg_user.id)
    if existing:
        return existing
    role_obj = await RoleDAO.get_by_name(
        "admin" if tg_user.id in settings.admin_ids else "student"
    )
    return await UserDAO.add(
        telegram_id=tg_user.id,
        username=tg_user.username,
        name=tg_user.full_name,
        role_id=role_obj.id if role_obj else None,
    )


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
        await _auto_register(message.from_user)
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
        await _auto_register(callback.from_user)
        await AuthService.invalidate_user(callback.from_user.id)
        permissions = await AuthService.get_user_permissions(callback.from_user.id)
    if not permissions:
        text = await UiTextService.get("menu.access_denied")
        await callback.message.edit_text(text)
        return

    await _render_menu(callback, permissions)


# ==== ADMIN ====
@router.callback_query(PermissionFilter("manage_cohorts"), F.data == "menu_cohorts")
async def cb_menu_cohorts(callback: CallbackQuery):
    await callback.answer()
    text = await UiTextService.get("menu.cohorts.title")
    try:
        await callback.message.edit_text(text, reply_markup=cohort_actions_keyboard())
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


async def _mentor_meetings_menu_kb():
    texts = await UiTextService.get_many(
        [
            "menu.mentor_meetings.btn.list",
            "menu.mentor_meetings.btn.create",
            "menu.mentor_meetings.btn.end_call",
            "menu.mentor_meetings.btn.feedback",
            "menu.back",
        ]
    )
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts["menu.mentor_meetings.btn.list"],
        callback_data="mentor_meetings_list",
    )
    kb.button(
        text=texts["menu.mentor_meetings.btn.create"],
        callback_data="meeting_create",
    )
    kb.button(
        text=texts["menu.mentor_meetings.btn.end_call"],
        callback_data="mentor_end_call",
    )
    kb.button(
        text=texts["menu.mentor_meetings.btn.feedback"],
        callback_data="menu_surveys",
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
    mentee_ids = [m.id for m in mentees]
    cohorts_map = await CohortDAO.get_cohorts_batch(mentee_ids)
    for mentee in mentees:
        display_name = mentee.doc_name or (mentee.user.name if mentee.user else "—")
        username = mentee.user.username if mentee.user else None
        username_display = f"@{e(username)}" if username else ""
        cohorts = cohorts_map.get(mentee.id, [])
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


@router.callback_query(
    PermissionFilter("manage_meetings"), F.data == "mentor_meetings_menu"
)
async def cb_mentor_meetings_menu(callback: CallbackQuery):
    await callback.answer()
    text = await UiTextService.get("menu.meetings.title")
    await callback.message.edit_text(
        text,
        reply_markup=await _mentor_meetings_menu_kb(),
    )


@router.callback_query(PermissionFilter("end_call"), F.data == "mentor_end_call")
async def cb_mentor_end_call(callback: CallbackQuery):
    await callback.answer()
    text = await _finish_active_call_text(callback.from_user.id)
    await callback.message.edit_text(
        text, reply_markup=await _mentor_meetings_menu_kb()
    )


@router.message(PermissionFilter("end_call"), Command("end_call"))
async def cmd_end_call(message: Message):
    text = await _finish_active_call_text(message.from_user.id)
    await message.answer(text, reply_markup=await _mentor_meetings_menu_kb())


async def _mentor_me_keyboard():
    texts = await UiTextService.get_many(["menu.mentor_me.btn.stats", "menu.back"])
    kb = InlineKeyboardBuilder()
    kb.button(text=texts["menu.mentor_me.btn.stats"], callback_data="mentor_my_stats")
    kb.button(text=texts["menu.back"], callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(PermissionFilter("view_own_info"), F.data == "mentor_me_info")
async def cb_mentor_me_info(callback: CallbackQuery):
    await callback.answer()

    mentors = await UserDAO.get_all(telegram_id=callback.from_user.id)
    mentor = mentors[0] if mentors else None
    if not mentor:
        text = await UiTextService.get("menu.not_found")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return

    role_display = mentor.role_rel.display_name if mentor.role_rel else "—"
    title = await UiTextService.get("menu.me.title")
    text = (
        f"{title}\n\n"
        f"Имя: <b>{e(mentor.name)}</b>\n"
        f"Юзернейм: @{e(mentor.username)}\n"
        f"Роль: <b>{e(role_display)}</b>\n"
    )

    try:
        await callback.message.edit_text(text, reply_markup=await _mentor_me_keyboard())
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
        cohorts = await CohortDAO.get_mentee_cohorts(mentee.id)
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
