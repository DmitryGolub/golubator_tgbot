from aiogram import Bot, Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import menu_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.keyboards.cohort import cohort_empty_keyboard, cohort_types_keyboard
from src.bot.utils import safe_edit_text
from src.services.auth import AuthService
from src.services.ui_text import UiTextService
from src.dao.user import UserDAO
from src.dao.mentee import MenteeDAO
from src.dao.mentor import MentorDAO
from src.dao.mentor_stats import MentorStatsDAO
from src.dao.cohort import CohortDAO

from src.bot.keyboards.meeting import mentor_meetings_keyboard
from src.services.call_flow import ActiveCallNotFoundError, CallFlowService
from src.bot.keyboards.utils import format_username_display
from src.utils.escape import e

router = Router(name="menu")


async def _check_has_mentor(user_id: int, permissions: set[str]) -> bool:
    if "propose_meetings" not in permissions:
        return True
    mentee = await MenteeDAO.find_by_telegram_id(user_id)
    return bool(mentee and mentee.mentor and mentee.mentor.telegram_id)


async def _check_has_directions(user_id: int, permissions: set[str]) -> bool:
    if "view_direction_students" not in permissions:
        return True
    return await CohortDAO.has_category_cohorts(user_id)


async def _ensure_user(tg_user):
    from src.bot.handlers.common.start import _ensure_user as _start_ensure_user

    return await _start_ensure_user(tg_user)


async def _send_or_edit(
    bot: Bot,
    chat_id: int,
    msg_id: int | None,
    text: str,
    markup,
    edit: bool,
) -> None:
    if edit and msg_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=markup,
            )
            return
        except TelegramBadRequest:
            pass
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)


async def render_menu_to(
    bot: Bot,
    chat_id: int,
    msg_id: int | None,
    user_id: int,
    *,
    tg_user=None,
    edit: bool = True,
) -> None:
    permissions = await AuthService.get_user_permissions(user_id)
    if not permissions and tg_user is not None:
        await _ensure_user(tg_user)
        await AuthService.invalidate_user(user_id)
        permissions = await AuthService.get_user_permissions(user_id)

    if not permissions:
        text = await UiTextService.get("menu.access_denied")
        await _send_or_edit(bot, chat_id, msg_id, text, None, edit)
        return

    has_mentor = await _check_has_mentor(user_id, permissions)
    has_directions = await _check_has_directions(user_id, permissions)
    text = await UiTextService.get("menu.title")
    markup = await menu_keyboard(
        permissions, has_mentor=has_mentor, has_directions=has_directions
    )
    await _send_or_edit(bot, chat_id, msg_id, text, markup, edit)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await render_menu_to(
        message.bot,
        message.chat.id,
        None,
        message.from_user.id,
        tg_user=message.from_user,
        edit=False,
    )


@router.callback_query(F.data == "back_to_menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await render_menu_to(
        callback.bot,
        callback.message.chat.id,
        callback.message.message_id,
        callback.from_user.id,
        tg_user=callback.from_user,
        edit=True,
    )


# ==== ADMIN ====
@router.callback_query(PermissionFilter("manage_cohorts"), F.data == "menu_cohorts")
async def cb_menu_cohorts(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    types_with_counts = await CohortDAO.get_types_with_value_counts()
    if not types_with_counts:
        text = await UiTextService.get("cohort.not_found")
        await safe_edit_text(callback, text, reply_markup=cohort_empty_keyboard())
        return

    header = await UiTextService.get("cohort.types.header")
    markup, types_map = cohort_types_keyboard(types_with_counts)
    await state.update_data(cohort_types_map=types_map)
    await safe_edit_text(callback, header, reply_markup=markup)


@router.callback_query(PermissionFilter("manage_mailings"), F.data == "menu_mailings")
async def cb_menu_mailings(callback: CallbackQuery):
    await callback.answer()
    text = "Рассылки перенесены в систему триггеров. Используйте меню триггеров."
    await safe_edit_text(callback, text, reply_markup=await back_to_menu_keyboard())


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

    duration_minutes = result.meeting.call_duration_minutes
    if duration_minutes is not None:
        hours, mins = divmod(duration_minutes, 60)
        duration_str = f"{hours}ч {mins}мин" if hours else f"{mins} мин"
    else:
        duration_str = "—"

    return await UiTextService.get(
        "menu.call_ended.with_meeting",
        id=str(result.meeting.id),
        start=f"{result.meeting.scheduled_at:%d.%m.%Y %H:%M}"
        if result.meeting.scheduled_at
        else "—",
        end=f"{result.meeting.completed_at:%d.%m.%Y %H:%M}"
        if result.meeting.completed_at
        else "—",
        duration=duration_str,
    )


@router.callback_query(
    PermissionFilter("view_students"), F.data == "mentor_students_menu"
)
async def cb_mentor_students_menu(callback: CallbackQuery):
    await callback.answer()

    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    if not mentees:
        text = await UiTextService.get("menu.students.empty")
        await safe_edit_text(
            callback,
            text,
            reply_markup=await _mentor_students_menu_kb(),
        )
        return

    header = await UiTextService.get("menu.students.header")
    lines = [header, ""]
    mentee_tids = [m.telegram_id for m in mentees if m.telegram_id is not None]
    cohorts_map = await CohortDAO.get_cohorts_batch(mentee_tids)
    for mentee in mentees:
        display_name = mentee.doc_name or (mentee.user.name if mentee.user else "—")
        username = mentee.user.username if mentee.user else None
        username_display = format_username_display(username, prefix="@")
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

    await safe_edit_text(
        callback,
        "\n".join(lines),
        reply_markup=await _mentor_students_menu_kb(),
    )


@router.callback_query(
    PermissionFilter("view_students"), F.data == "mentor_students_add"
)
async def cb_mentor_students_add(callback: CallbackQuery):
    await callback.answer()
    permissions = await AuthService.get_user_permissions(callback.from_user.id)
    has_mentor = await _check_has_mentor(callback.from_user.id, permissions)
    has_directions = await _check_has_directions(callback.from_user.id, permissions)
    await safe_edit_text(
        callback,
        "Выберите менти для изменения статуса.",
        reply_markup=await menu_keyboard(
            permissions, has_mentor=has_mentor, has_directions=has_directions
        ),
    )


@router.callback_query(PermissionFilter("end_call"), F.data == "mentor_end_call")
async def cb_mentor_end_call(callback: CallbackQuery):
    await callback.answer()
    text = await _finish_active_call_text(callback.from_user.id)
    from src.bot.handlers.meeting import prepare_meetings_view

    view = await prepare_meetings_view(callback.from_user.id, hide_past=True)
    await safe_edit_text(callback, text)
    await callback.message.answer(
        view.text,
        reply_markup=mentor_meetings_keyboard(
            view.visible, page=0, viewer_id=callback.from_user.id
        ),
    )


@router.message(PermissionFilter("end_call"), Command("end_call"))
async def cmd_end_call(message: Message):
    text = await _finish_active_call_text(message.from_user.id)
    from src.bot.handlers.meeting import prepare_meetings_view

    view = await prepare_meetings_view(message.from_user.id, hide_past=True)
    await message.answer(text)
    await message.answer(
        view.text,
        reply_markup=mentor_meetings_keyboard(
            view.visible, page=0, viewer_id=message.from_user.id
        ),
    )


@router.callback_query(PermissionFilter("view_own_info"), F.data == "mentor_me_info")
async def cb_mentor_me_info(callback: CallbackQuery):
    await callback.answer()

    mentor_id = callback.from_user.id
    mentor = await MentorDAO.find_by_telegram_id(mentor_id)
    if not mentor:
        text = await UiTextService.get("menu.not_found")
        await safe_edit_text(callback, text, reply_markup=await back_to_menu_keyboard())
        return

    stats = await MentorStatsDAO.get_stats(mentor_id=mentor_id)

    title = await UiTextService.get("menu.me.title")
    lines = [
        f"{title}\n",
        f"Имя: <b>{e(mentor.name)}</b>",
        f"Юзернейм:{format_username_display(mentor.user.username if mentor.user else None, prefix=' @')}",
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

    await safe_edit_text(callback, text, reply_markup=await back_to_menu_keyboard())


# ==== STUDENT ====
@router.callback_query(PermissionFilter("view_own_info"), F.data == "student_me_info")
async def cb_student_me_info(callback: CallbackQuery):
    await callback.answer()

    students = await UserDAO.get_all(telegram_id=callback.from_user.id)
    student = students[0] if students else None
    if not student:
        text = await UiTextService.get("menu.not_found")
        await safe_edit_text(callback, text, reply_markup=await back_to_menu_keyboard())
        return

    mentee = await MenteeDAO.find_by_telegram_id(callback.from_user.id)
    mentor_name = "Отсутствует"
    mentor_username = ""
    mentee_state = "—"
    if mentee:
        if mentee.mentor:
            mentor_name = mentee.mentor.name or "Отсутствует"
            mentor_username = format_username_display(
                mentee.mentor.user.username if mentee.mentor.user else None,
                prefix="@",
            )
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
        f"Юзернейм:{format_username_display(student.username, prefix=' @')}\n"
        f"Роль: <b>{e(role_display)}</b>\n"
        f"Мой ментор: <b>{e(mentor_name)}</b> {mentor_username}\n"
        f"Состояние: <b>{e(mentee_state)}</b>\n"
    )

    await safe_edit_text(callback, text, reply_markup=await back_to_menu_keyboard())
