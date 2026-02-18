from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta, date, timezone
from aiogram.exceptions import TelegramBadRequest

from src.bot.callbacks.meeting import (
    ChooseMeetingStudentCB,
    DeleteMeetingCB,
    ChooseMeetingDateCB,
    NavigateMeetingMonthCB,
    ChooseMeetingTimeCB,
)
from src.bot.filters.role import RoleFilter
from src.bot.keyboards.meeting import (
    mentor_meetings_keyboard,
    meeting_cancel_keyboard,
    meeting_students_keyboard,
    meeting_calendar_keyboard,
    meeting_time_keyboard,
)
from src.bot.keyboards.menu import menu_keyboard
from src.bot.states.meeting import CreateMeetingFSM
from src.dao.meeting import MeetingDAO
from src.dao.user import UserDAO
from src.models.user import Role
import logging
from src.tasks.meeting import (
    notify_meeting_created,
    notify_meeting_reminder,
    complete_meeting as complete_meeting_task,
)

logger = logging.getLogger(__name__)
MOSCOW_TZ = timezone(timedelta(hours=3))
router = Router(name="meetings")
router.message.filter(RoleFilter([Role.mentor, Role.student]))
router.callback_query.filter(RoleFilter([Role.mentor, Role.student]))


def _format_meetings(meetings, viewer_id: int, role: Role) -> str:
    if not meetings:
        return "Список созвонов пуст."

    lines = ["<b>Мои созвоны:</b>", ""]
    for meeting in meetings:
        mentor = next((p for p in meeting.participants if p.role == Role.mentor), None)
        student = next((p for p in meeting.participants if p.role == Role.student), None)

        # fallback: если роль не подтянулась, берем второго участника не равного ментору
        if not student:
            student = next(
                (
                    p
                    for p in meeting.participants
                    if mentor and p.telegram_id != mentor.telegram_id
                ),
                None,
            )

        if role == Role.mentor and mentor and mentor.telegram_id != viewer_id:
            continue
        if role == Role.student and student and student.telegram_id != viewer_id:
            continue

        mentor_text = f"Ментор: <b>{mentor.name}</b> @{mentor.username}" if mentor else "Ментор: —"
        student_text = f"Ученик: <b>{student.name}</b> @{student.username}" if student else "Ученик: —"
        desc = meeting.description or "—"
        link = meeting.meeting_link or "—"
        if meeting.scheduled_at:
            try:
                # отображаем как записано (локальное время встречи)
                if meeting.scheduled_at.tzinfo:
                    date_str = meeting.scheduled_at.astimezone(meeting.scheduled_at.tzinfo).strftime(
                        "%d.%m.%Y %H:%M MSK"
                    )
                else:
                    date_str = meeting.scheduled_at.strftime("%d.%m.%Y %H:%M MSK")
            except Exception:
                date_str = meeting.scheduled_at.isoformat()
        else:
            date_str = "—"

        lines.append(
            f"🗓 Созвон #{meeting.id}\n"
            f"{mentor_text}\n"
            f"{student_text}\n"
            f"Когда: {date_str}\n"
            f"Описание: {desc}\n"
            f"Ссылка: {link}\n"
        )
    return "\n".join(lines)


@router.callback_query(RoleFilter([Role.mentor]), F.data == "mentor_meetings_list")
async def cb_mentor_meetings(callback: CallbackQuery):
    await callback.answer()
    meetings = await MeetingDAO.get_for_user(callback.from_user.id, hide_past=True)

    text = _format_meetings(meetings, callback.from_user.id, Role.mentor)
    await callback.message.edit_text(text, reply_markup=mentor_meetings_keyboard(meetings))


@router.callback_query(RoleFilter([Role.student]), F.data == "student_meetings")
async def cb_student_meetings(callback: CallbackQuery):
    await callback.answer()
    meetings = await MeetingDAO.get_for_user(callback.from_user.id, hide_past=True)

    text = _format_meetings(meetings, callback.from_user.id, Role.student)
    try:
        await callback.message.edit_text(text, reply_markup=menu_keyboard(Role.student))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(RoleFilter([Role.mentor]), F.data == "meeting_create")
async def cb_meeting_create(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    students = await UserDAO.get_all(mentor_id=callback.from_user.id)
    if not students:
        await callback.message.edit_text(
            "У вас пока нет учеников.",
            reply_markup=menu_keyboard(Role.mentor),
        )
        return

    await state.set_state(CreateMeetingFSM.choosing_student)
    await callback.message.edit_text(
        "Выберите ученика для созвона:",
        reply_markup=meeting_students_keyboard(students),
    )


@router.callback_query(
    RoleFilter([Role.mentor]),
    StateFilter(CreateMeetingFSM.choosing_student),
    ChooseMeetingStudentCB.filter(),
)
async def cb_choose_meeting_student(
    callback: CallbackQuery,
    callback_data: ChooseMeetingStudentCB,
    state: FSMContext,
):
    await callback.answer()

    await state.update_data(student_id=callback_data.student_id)
    await state.set_state(CreateMeetingFSM.waiting_description)

    await callback.message.edit_text(
        "Введите описание встречи:",
        reply_markup=meeting_cancel_keyboard(),
    )


@router.message(RoleFilter([Role.mentor]), StateFilter(CreateMeetingFSM.waiting_description))
async def msg_meeting_description(message: Message, state: FSMContext):
    description = message.text.strip() if message.text else ""
    await state.update_data(description=description)
    await state.set_state(CreateMeetingFSM.waiting_date)

    await message.answer(
        "Выберите дату встречи:",
        reply_markup=meeting_calendar_keyboard(date.today()),
    )


@router.callback_query(
    RoleFilter([Role.mentor]),
    StateFilter(CreateMeetingFSM.waiting_date),
    NavigateMeetingMonthCB.filter(),
)
async def cb_meeting_nav_month(
    callback: CallbackQuery,
    callback_data: NavigateMeetingMonthCB,
    state: FSMContext,
):
    await callback.answer()
    year = callback_data.year
    month = callback_data.month + callback_data.delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    await callback.message.edit_reply_markup(
        reply_markup=meeting_calendar_keyboard(date(year, month, 1))
    )


@router.callback_query(
    RoleFilter([Role.mentor]),
    StateFilter(CreateMeetingFSM.waiting_date),
    ChooseMeetingDateCB.filter(),
)
async def cb_meeting_choose_date(
    callback: CallbackQuery,
    callback_data: ChooseMeetingDateCB,
    state: FSMContext,
):
    await callback.answer()
    chosen_date = date(callback_data.year, callback_data.month, callback_data.day)
    await state.update_data(chosen_date=chosen_date.isoformat())
    await state.set_state(CreateMeetingFSM.waiting_time)

    await callback.message.edit_text(
        f"Дата выбрана: {chosen_date:%d.%m.%Y}\nТеперь выберите время или введите его в формате HH:MM.",
        reply_markup=meeting_time_keyboard(chosen_date.isoformat()),
    )


def _parse_time(value: str) -> str | None:
    raw = (value or "").strip().replace(":", "")
    if len(raw) == 4 and raw.isdigit():
        hh, mm = raw[:2], raw[2:]
        if 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
            return f"{hh}:{mm}"
    return None


@router.message(RoleFilter([Role.mentor]), StateFilter(CreateMeetingFSM.waiting_time))
async def msg_meeting_time(message: Message, state: FSMContext):
    parsed = _parse_time(message.text)
    if not parsed:
        await message.answer(
            "Не удалось распознать время. Введите в формате HH:MM, например 18:00.",
            reply_markup=meeting_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    chosen_date = data.get("chosen_date")
    if not chosen_date:
        await state.clear()
        await message.answer("Дата не выбрана, начните заново.", reply_markup=menu_keyboard(Role.mentor))
        return

    scheduled_iso = f"{chosen_date} {parsed}"
    await state.update_data(scheduled_at=scheduled_iso)
    await state.set_state(CreateMeetingFSM.waiting_link)

    await message.answer(
        "Введите ссылку на встречу (Telemost, Zoom, Google Meet и т.д.):",
        reply_markup=meeting_cancel_keyboard(),
    )


@router.callback_query(
    RoleFilter([Role.mentor]),
    StateFilter(CreateMeetingFSM.waiting_time),
    ChooseMeetingTimeCB.filter(),
)
async def cb_meeting_choose_time(
    callback: CallbackQuery,
    callback_data: ChooseMeetingTimeCB,
    state: FSMContext,
):
    await callback.answer()
    data = await state.get_data()
    chosen_date = data.get("chosen_date")
    if not chosen_date:
        await state.clear()
        await callback.message.edit_text("Дата не выбрана, начните заново.", reply_markup=menu_keyboard(Role.mentor))
        return

    hhmm = callback_data.t
    hh, mm = hhmm[:2], hhmm[2:]
    scheduled_iso = f"{chosen_date} {hh}:{mm}"
    await state.update_data(scheduled_at=scheduled_iso)
    await state.set_state(CreateMeetingFSM.waiting_link)

    await callback.message.edit_text(
        "Введите ссылку на встречу (Telemost, Zoom, Google Meet и т.д.):",
        reply_markup=meeting_cancel_keyboard(),
    )


def _parse_datetime(value: str) -> datetime | None:
    # Support ISO and "YYYY-MM-DD HH:MM"
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y%m%d%H%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt  # хранится как введено (локальное время)
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(value)
        return dt  # не трогаем tz, если есть, иначе оставляем naive
    except Exception:
        return None


def _to_utc_assuming_msk(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MOSCOW_TZ)
    return dt.astimezone(timezone.utc)


def _schedule_meeting_tasks(meeting) -> None:
    meeting_id = meeting.id
    scheduled_at = meeting.scheduled_at

    scheduled_utc = _to_utc_assuming_msk(scheduled_at)

    now = datetime.now(timezone.utc)

    # immediate notification
    notify_meeting_created.delay(meeting_id)
    logger.info("Scheduled notify_created for meeting %s", meeting_id)

    if scheduled_utc:
        reminder_eta = scheduled_utc - timedelta(minutes=5)
        if reminder_eta > now:
            notify_meeting_reminder.apply_async(args=[meeting_id], eta=reminder_eta)
            logger.info("Scheduled reminder for meeting %s at %s", meeting_id, reminder_eta)

        if scheduled_utc <= now:
            complete_meeting_task.delay(meeting_id)
            logger.info("Meeting %s already in past, completing now", meeting_id)
        else:
            complete_meeting_task.apply_async(args=[meeting_id], eta=scheduled_utc)
            logger.info("Scheduled completion for meeting %s at %s", meeting_id, scheduled_utc)


@router.message(RoleFilter([Role.mentor]), StateFilter(CreateMeetingFSM.waiting_link))
async def msg_meeting_link(message: Message, state: FSMContext):
    link = message.text.strip() if message.text else ""
    data = await state.get_data()

    student_id = data.get("student_id")
    description = data.get("description")
    scheduled_at_raw = data.get("scheduled_at")
    scheduled_at = None
    if scheduled_at_raw:
        scheduled_at = _parse_datetime(scheduled_at_raw)

    if not scheduled_at:
        await message.answer(
            "Не удалось сохранить дату/время. Попробуйте создать созвон заново.",
            reply_markup=menu_keyboard(Role.mentor),
        )
        await state.clear()
        return

    meeting = await MeetingDAO.create_with_participants(
        description=description,
        meeting_link=link,
        scheduled_at=scheduled_at,
        mentor_id=message.from_user.id,
        student_id=student_id,
    )
    _schedule_meeting_tasks(meeting)
    await state.clear()

    await message.answer(
        "Созвон успешно создан.",
        reply_markup=menu_keyboard(Role.mentor),
    )


@router.callback_query(RoleFilter([Role.mentor]), DeleteMeetingCB.filter())
async def cb_delete_meeting(callback: CallbackQuery, callback_data: DeleteMeetingCB):
    await callback.answer()

    deleted = await MeetingDAO.delete_for_mentor(
        meeting_id=callback_data.meeting_id,
        mentor_id=callback.from_user.id,
    )

    if not deleted:
        await callback.message.edit_text(
            "Созвон не найден или у вас нет прав на удаление.",
            reply_markup=mentor_meetings_keyboard(),
        )
        return

    meetings = await MeetingDAO.get_for_user(callback.from_user.id)
    text = _format_meetings(meetings, callback.from_user.id, Role.mentor)
    await callback.message.edit_text(
        f"Созвон #{callback_data.meeting_id} удалён.\n\n{text}",
        reply_markup=mentor_meetings_keyboard(meetings),
    )


@router.callback_query(
    RoleFilter([Role.mentor]),
    StateFilter(
        CreateMeetingFSM.choosing_student,
        CreateMeetingFSM.waiting_description,
        CreateMeetingFSM.waiting_date,
        CreateMeetingFSM.waiting_time,
        CreateMeetingFSM.waiting_link,
    ),
    F.data == "meeting_create_cancel",
)
async def cb_meeting_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "Создание созвона отменено.",
        reply_markup=menu_keyboard(Role.mentor),
    )
