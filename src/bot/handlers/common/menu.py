from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import menu_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.keyboards.user import user_actions_keyboard
from src.bot.keyboards.cohort import cohort_actions_keyboard
from src.services.auth import AuthService
from src.services.ui_text import UiTextService
from src.dao.user import UserDAO
from src.dao.notion_cache import NotionCacheDAO

from src.services.call_flow import ActiveCallNotFoundError, CallFlowService
from src.models.user import Role
from src.utils.escape import e

router = Router(name="menu")


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
        text = await UiTextService.get("menu.access_denied")
        await message.answer(text)
        return

    await _render_menu(message, permissions)


@router.callback_query(F.data == "back_to_menu")
async def cb_menu(callback: CallbackQuery):
    await callback.answer()

    permissions = await AuthService.get_user_permissions(callback.from_user.id)
    if not permissions:
        text = await UiTextService.get("menu.access_denied")
        await callback.message.edit_text(text)
        return

    await _render_menu(callback, permissions)


# ==== ADMIN ====
@router.callback_query(PermissionFilter("manage_users"), F.data == "menu_users")
async def cb_menu_users(callback: CallbackQuery):
    await callback.answer()
    text = await UiTextService.get("menu.users.title")
    try:
        await callback.message.edit_text(text, reply_markup=user_actions_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


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
            "menu.mentor_students.btn.list",
            "menu.mentor_students.btn.update",
            "menu.back",
        ]
    )
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts["menu.mentor_students.btn.list"],
        callback_data="mentor_students_list",
    )
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

    if result.meeting is None:
        return await UiTextService.get(
            "menu.call_ended.no_meeting",
            start=f"{result.call.started_at:%d.%m.%Y %H:%M}",
            end=f"{result.call.ended_at:%d.%m.%Y %H:%M}",
        )

    return await UiTextService.get(
        "menu.call_ended.with_meeting",
        id=str(result.meeting.id),
        start=f"{result.call.started_at:%d.%m.%Y %H:%M}",
        end=f"{result.call.ended_at:%d.%m.%Y %H:%M}",
    )


@router.callback_query(
    PermissionFilter("view_students"), F.data == "mentor_students_menu"
)
async def cb_mentor_students_menu(callback: CallbackQuery):
    await callback.answer()
    text = await UiTextService.get("menu.students.title")
    try:
        await callback.message.edit_text(
            text,
            reply_markup=await _mentor_students_menu_kb(),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(
    PermissionFilter("view_students"), F.data == "mentor_students_list"
)
async def cb_mentor_students_list(callback: CallbackQuery):
    await callback.answer()

    students = await UserDAO.get_all(mentor_id=callback.from_user.id)
    if not students:
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
    student_ids = [s.telegram_id for s in students]
    cohorts_map = await NotionCacheDAO.get_cohorts_batch(student_ids)
    for student in students:
        role_display = student.role_rel.display_name if student.role_rel else "—"
        cohorts = cohorts_map.get(student.telegram_id, [])
        categories = [c.cohort_value for c in cohorts if c.cohort_type == "Category"]
        cohort_display = ", ".join(categories) if categories else "Отсутствует"
        lines.append(
            f"👤 <b>{e(student.name)}</b> @{e(student.username)}\n"
            f"   • Направления: <b>{e(cohort_display)}</b>\n"
            f"   • Роль: <b>{e(role_display)}</b>\n"
            f"   • Состояние: <b>{e(student.state.value if student.state else '—')}</b>\n"
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
    if mentor.role == Role.student and mentor.state:
        text += f"Состояние: <b>{e(mentor.state.value)}</b>\n"

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

    mentor_name = student.mentor.name if student.mentor else "Отсутствует"
    mentor_username = f"@{student.mentor.username}" if student.mentor else ""
    role_display = student.role_rel.display_name if student.role_rel else "—"

    title = await UiTextService.get("menu.me.title")
    text = (
        f"{title}\n\n"
        f"Имя: <b>{e(student.name)}</b>\n"
        f"Юзернейм: @{e(student.username)}\n"
        f"Роль: <b>{e(role_display)}</b>\n"
        f"Мой ментор: <b>{e(mentor_name)}</b> {e(mentor_username)}\n"
        f"Состояние: <b>{e(student.state.value if student.state else '—')}</b>\n"
    )

    try:
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
