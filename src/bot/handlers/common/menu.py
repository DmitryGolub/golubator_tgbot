from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.filters.role import RoleFilter
from src.bot.keyboards.menu import menu_keyboard
from src.bot.keyboards.mailings import mailings_menu_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.keyboards.user import user_actions_keyboard
from src.bot.keyboards.cohort import cohort_actions_keyboard
from src.models.user import Role
from src.utils.auth import get_user_role
from src.dao.user import UserDAO

router = Router(name="menu")
router.message.filter(RoleFilter([Role.admin, Role.mentor, Role.student]))
router.callback_query.filter(RoleFilter([Role.admin, Role.mentor, Role.student]))


async def _render_menu(message_or_callback, role: Role):
    text = "Список доступных команд"
    markup = menu_keyboard(role)

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
    role = await get_user_role(message.from_user.id)
    if not role:
        await message.answer("Доступ запрещен.")
        return

    await _render_menu(message, role)


@router.callback_query(F.data == "back_to_menu")
async def cb_menu(callback: CallbackQuery):
    await callback.answer()

    role = await get_user_role(callback.from_user.id)
    if not role:
        await callback.message.edit_text("Доступ запрещен.")
        return

    await _render_menu(callback, role)


# ==== ADMIN ====
@router.callback_query(RoleFilter([Role.admin]), F.data == "menu_users")
async def cb_menu_users(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("👥 Меню Пользователей", reply_markup=user_actions_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(RoleFilter([Role.admin]), F.data == "menu_cohorts")
async def cb_menu_cohorts(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("👥 Меню Когорт", reply_markup=cohort_actions_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(RoleFilter([Role.admin]), F.data == "menu_mailings")
async def cb_menu_mailings(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text("👥 Меню Рассылок", reply_markup=mailings_menu_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise

# ==== MENTOR ====

def _mentor_students_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Список учеников", callback_data="mentor_students_list")
    kb.button(text="Изменить статус ученика", callback_data="mentor_update_student")
    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def _mentor_meetings_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Список созвонов", callback_data="mentor_meetings_list")
    kb.button(text="Добавить созвон", callback_data="meeting_create")
    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(RoleFilter([Role.mentor]), F.data == "mentor_students_menu")
async def cb_mentor_students_menu(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text(
            "Ученики:",
            reply_markup=_mentor_students_menu_kb(),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(RoleFilter([Role.mentor]), F.data == "mentor_students_list")
async def cb_mentor_students_list(callback: CallbackQuery):
    await callback.answer()

    students = await UserDAO.get_all(mentor_id=callback.from_user.id)
    if not students:
        try:
            await callback.message.edit_text(
                "Список учеников пуст.",
                reply_markup=_mentor_students_menu_kb(),
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
        return

    lines = ["<b>Мои ученики:</b>", ""]
    for student in students:
        cohort_name = student.cohort.name if student.cohort else "Отсутствует"
        lines.append(
            f"👤 <b>{student.name}</b> @{student.username}\n"
            f"   • Когорта: <b>{cohort_name}</b>\n"
            f"   • Роль: <b>{student.role.value}</b>\n"
            f"   • Состояние: <b>{student.state.value}</b>\n"
        )

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=_mentor_students_menu_kb(),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(RoleFilter([Role.mentor]), F.data == "mentor_students_add")
async def cb_mentor_students_add(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "Выберите ученика для изменения статуса.",
        reply_markup=menu_keyboard(Role.mentor),
    )


@router.callback_query(RoleFilter([Role.mentor]), F.data == "mentor_meetings_menu")
async def cb_mentor_meetings_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "Созвоны:",
        reply_markup=_mentor_meetings_menu_kb(),
    )


@router.callback_query(RoleFilter([Role.mentor]), F.data == "mentor_me_info")
async def cb_mentor_me_info(callback: CallbackQuery):
    await callback.answer()

    mentors = await UserDAO.get_all(telegram_id=callback.from_user.id)
    mentor = mentors[0] if mentors else None
    if not mentor:
        await callback.message.edit_text("Профиль не найден.", reply_markup=back_to_menu_keyboard())
        return

    cohort_name = mentor.cohort.name if mentor.cohort else "Отсутствует"

    text = (
        "<b>Моя информация:</b>\n\n"
        f"Имя: <b>{mentor.name}</b>\n"
        f"Юзернейм: @{mentor.username}\n"
        f"Роль: <b>{mentor.role.value}</b>\n"
        f"Когорта: <b>{cohort_name}</b>\n"
        f"Состояние: <b>{mentor.state.value}</b>\n"
    )

    try:
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


# ==== STUDENT ====
@router.callback_query(RoleFilter([Role.student]), F.data == "student_me_info")
async def cb_student_me_info(callback: CallbackQuery):
    await callback.answer()

    students = await UserDAO.get_all(telegram_id=callback.from_user.id)
    student = students[0] if students else None
    if not student:
        await callback.message.edit_text("Профиль не найден.", reply_markup=back_to_menu_keyboard())
        return

    cohort_name = student.cohort.name if student.cohort else "Отсутствует"
    mentor_name = student.mentor.name if student.mentor else "Отсутствует"
    mentor_username = f"@{student.mentor.username}" if student.mentor else ""

    text = (
        "<b>Моя информация:</b>\n\n"
        f"Имя: <b>{student.name}</b>\n"
        f"Юзернейм: @{student.username}\n"
        f"Роль: <b>{student.role.value}</b>\n"
        f"Когорта: <b>{cohort_name}</b>\n"
        f"Мой ментор: <b>{mentor_name}</b> {mentor_username}\n"
        f"Состояние: <b>{student.state.value}</b>\n"
    )

    try:
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise

# ==== MENTOR/STUDENT callbacks now live in meeting handler ====