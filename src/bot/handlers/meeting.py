from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta, date, timezone

from src.utils.tz import MSK
from aiogram.exceptions import TelegramBadRequest

from src.bot.callbacks.meeting import (
    ChooseMeetingStudentCB,
    ChooseMeetingTypeCB,
    DeleteMeetingCB,
    StartMeetingCallCB,
    ChooseMeetingDateCB,
    NavigateMeetingMonthCB,
    ChooseMeetingTimeCB,
)
from src.bot.callbacks.pagination import PageNavCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.meeting import (
    mentor_meetings_keyboard,
    meeting_cancel_keyboard,
    meeting_skip_cancel_keyboard,
    meeting_students_keyboard,
    meeting_type_keyboard,
    meeting_calendar_keyboard,
    meeting_time_keyboard,
)
from src.bot.keyboards.menu import menu_keyboard
from src.bot.states.meeting import CreateMeetingFSM
from src.dao.meeting import MeetingDAO
from src.dao.mentor import MentorDAO
from src.dao.user import UserDAO
from src.dao.mentee import MenteeDAO
from src.models.meeting import CallStatus
from src.services.auth import AuthService
from src.utils.escape import e
import logging
from src.tasks.meeting import (
    notify_meeting_created,
    notify_meeting_reminder,
)
from src.services.call_flow import (
    ActiveCallAlreadyExistsError,
    CallAlreadyExistsError,
    CallFlowService,
    MeetingAlreadyCompletedError,
    MeetingNotFoundError,
    MeetingStudentNotFoundError,
    MentorNotInMeetingError,
)

logger = logging.getLogger(__name__)
MOSCOW_TZ = timezone(timedelta(hours=3))
router = Router(name="meetings")
router.message.filter(PermissionFilter(["manage_meetings", "view_own_meetings"]))
router.callback_query.filter(PermissionFilter(["manage_meetings", "view_own_meetings"]))


async def _menu_kb(user_id: int):
    perms = await AuthService.get_user_permissions(user_id)
    return await menu_keyboard(perms)


def _format_meetings(
    meetings, viewer_id: int, viewer_is_mentor: bool, mentor_tg_ids: set[int]
) -> str:
    if not meetings:
        return "Список созвонов пуст."

    lines = ["<b>Мои созвоны:</b>", ""]
    for meeting in meetings:
        mentor = next(
            (p for p in meeting.participants if p.telegram_id in mentor_tg_ids),
            None,
        )

        # fallback: identify mentor by meeting.mentor_telegram_id
        if not mentor and meeting.mentor_telegram_id:
            mentor = next(
                (
                    p
                    for p in meeting.participants
                    if p.telegram_id == meeting.mentor_telegram_id
                ),
                None,
            )

        # student: remaining participant or mentee_telegram_tag
        student = next(
            (
                p
                for p in meeting.participants
                if not mentor or p.telegram_id != mentor.telegram_id
            ),
            None,
        )

        if viewer_is_mentor and mentor and mentor.telegram_id != viewer_id:
            continue
        if not viewer_is_mentor and student and student.telegram_id != viewer_id:
            continue

        mentor_text = (
            f"Ментор: <b>{e(mentor.name)}</b> @{e(mentor.username)}"
            if mentor
            else "Ментор: —"
        )
        if student:
            student_text = f"Ученик: <b>{e(student.name)}</b> @{e(student.username)}"
        elif meeting.mentee_telegram_tag:
            student_text = f"Ученик: {e(meeting.mentee_telegram_tag)}"
        else:
            student_text = "Ученик: —"
        desc = e(meeting.description) if meeting.description else "—"
        link = e(meeting.meeting_link) if meeting.meeting_link else "—"
        if meeting.scheduled_at:
            try:
                if meeting.scheduled_at.tzinfo:
                    date_str = meeting.scheduled_at.astimezone(
                        meeting.scheduled_at.tzinfo
                    ).strftime("%d.%m.%Y %H:%M MSK")
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


@router.callback_query(
    PermissionFilter("manage_meetings"),
    F.data.in_({"mentor_meetings_list", "mentor_meetings_menu"}),
)
async def cb_mentor_meetings(callback: CallbackQuery):
    await callback.answer()
    meetings = await MeetingDAO.get_for_user(callback.from_user.id)
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    text = _format_meetings(
        meetings,
        callback.from_user.id,
        viewer_is_mentor=True,
        mentor_tg_ids=mentor_tg_ids,
    )
    await callback.message.edit_text(
        text, reply_markup=mentor_meetings_keyboard(meetings)
    )


@router.callback_query(
    PermissionFilter("view_own_meetings"), F.data == "student_meetings"
)
async def cb_student_meetings(callback: CallbackQuery):
    await callback.answer()
    meetings = await MeetingDAO.get_for_user(callback.from_user.id)
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    text = _format_meetings(
        meetings,
        callback.from_user.id,
        viewer_is_mentor=False,
        mentor_tg_ids=mentor_tg_ids,
    )
    try:
        await callback.message.edit_text(
            text, reply_markup=await _menu_kb(callback.from_user.id)
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(PermissionFilter("manage_meetings"), StartMeetingCallCB.filter())
async def cb_start_meeting_call(
    callback: CallbackQuery,
    callback_data: StartMeetingCallCB,
):
    await callback.answer()

    service = CallFlowService()

    try:
        await service.start_call(
            mentor_id=callback.from_user.id,
            meeting_id=callback_data.meeting_id,
        )
    except MeetingNotFoundError:
        text = "Созвон не найден."
    except MentorNotInMeetingError:
        text = "У вас нет доступа к этому созвону."
    except MeetingAlreadyCompletedError:
        text = "Этот созвон уже завершён."
    except MeetingStudentNotFoundError:
        text = "Не удалось определить ученика для этого созвона."
    except ActiveCallAlreadyExistsError as exc:
        if exc.meeting.id == callback_data.meeting_id:
            text = "Этот созвон уже запущен и числится активным."
        else:
            text = (
                "У вас уже есть активный созвон. "
                "Сначала завершите его через кнопку или команду /end_call."
            )
    except CallAlreadyExistsError as exc:
        if exc.meeting.call_status == CallStatus.ongoing:
            text = "Этот созвон уже запущен и числится активным."
        else:
            text = "Для этого созвона уже есть завершённая сессия."
    else:
        text = (
            f"✅ Созвон по встрече #{callback_data.meeting_id} начат.\n\n"
            "После окончания используйте кнопку «Завершить активный созвон» "
            "или команду /end_call."
        )

    meetings = await MeetingDAO.get_for_user(callback.from_user.id)
    await callback.message.edit_text(
        text,
        reply_markup=mentor_meetings_keyboard(meetings),
    )


@router.callback_query(PermissionFilter("manage_meetings"), F.data == "meeting_create")
async def cb_meeting_create(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    if not mentees:
        await callback.message.edit_text(
            "У вас пока нет учеников.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        return

    await state.set_state(CreateMeetingFSM.choosing_student)
    await callback.message.edit_text(
        "Выберите ученика для созвона:",
        reply_markup=meeting_students_keyboard(mentees),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_student),
    ChooseMeetingStudentCB.filter(),
)
async def cb_choose_meeting_student(
    callback: CallbackQuery,
    callback_data: ChooseMeetingStudentCB,
    state: FSMContext,
):
    await callback.answer()

    mentee = await MenteeDAO.find_one_or_none(id=callback_data.mentee_id)
    if not mentee:
        await callback.message.edit_text(
            "Ученик не найден.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        await state.clear()
        return

    await state.update_data(
        student_id=mentee.telegram_id,
        mentee_id=mentee.id,
    )
    await state.set_state(CreateMeetingFSM.choosing_type)

    await callback.message.edit_text(
        "Выберите тип встречи:",
        reply_markup=meeting_type_keyboard(),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_type),
    ChooseMeetingTypeCB.filter(),
)
async def cb_choose_meeting_type(
    callback: CallbackQuery,
    callback_data: ChooseMeetingTypeCB,
    state: FSMContext,
):
    await callback.answer()
    from src.bot.keyboards.meeting import MEETING_TYPES

    await state.update_data(event_type=MEETING_TYPES[callback_data.type_idx])
    await state.set_state(CreateMeetingFSM.waiting_description)

    await callback.message.edit_text(
        "Введите описание встречи:",
        reply_markup=meeting_cancel_keyboard(),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_type),
    F.data == "meeting_skip_type",
)
async def cb_skip_meeting_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(CreateMeetingFSM.waiting_description)

    await callback.message.edit_text(
        "Введите описание встречи:",
        reply_markup=meeting_cancel_keyboard(),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_type),
    PageNavCB.filter(F.menu == "meeting_types"),
)
async def cb_meeting_types_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=meeting_type_keyboard(page=callback_data.page)
    )


@router.message(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.waiting_description),
)
async def msg_meeting_description(message: Message, state: FSMContext):
    description = message.text.strip() if message.text else ""
    await state.update_data(description=description)
    await state.set_state(CreateMeetingFSM.waiting_date)

    await message.answer(
        "Выберите дату встречи:",
        reply_markup=meeting_calendar_keyboard(datetime.now(MSK).date()),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
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
    PermissionFilter("manage_meetings"),
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
        reply_markup=meeting_time_keyboard(),
    )


def _parse_time(value: str) -> str | None:
    raw = (value or "").strip().replace(":", "")
    if len(raw) == 4 and raw.isdigit():
        hh, mm = raw[:2], raw[2:]
        if 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
            return f"{hh}:{mm}"
    return None


@router.message(
    PermissionFilter("manage_meetings"), StateFilter(CreateMeetingFSM.waiting_time)
)
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
        await message.answer(
            "Дата не выбрана, начните заново.",
            reply_markup=await _menu_kb(message.from_user.id),
        )
        return

    scheduled_iso = f"{chosen_date} {parsed}"
    await state.update_data(scheduled_at=scheduled_iso)
    await state.set_state(CreateMeetingFSM.waiting_link)

    await message.answer(
        "Введите ссылку на встречу (Telemost, Zoom, Google Meet и т.д.):",
        reply_markup=meeting_skip_cancel_keyboard(),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
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
        await callback.message.edit_text(
            "Дата не выбрана, начните заново.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        return

    hhmm = callback_data.t
    hh, mm = hhmm[:2], hhmm[2:]
    scheduled_iso = f"{chosen_date} {hh}:{mm}"
    await state.update_data(scheduled_at=scheduled_iso)
    await state.set_state(CreateMeetingFSM.waiting_link)

    await callback.message.edit_text(
        "Введите ссылку на встречу (Telemost, Zoom, Google Meet и т.д.):",
        reply_markup=meeting_skip_cancel_keyboard(),
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
            return dt
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(value)
        return dt
    except Exception:
        return None


def _to_utc_assuming_msk(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MOSCOW_TZ)
    return dt.astimezone(timezone.utc)


async def _schedule_meeting_tasks(meeting, mentor_id: int, student_id: int) -> None:
    meeting_id = meeting.id
    scheduled_at = meeting.scheduled_at

    scheduled_utc = _to_utc_assuming_msk(scheduled_at)

    # Legacy notifications (kept for backward compatibility during transition)
    notify_meeting_created.delay(meeting_id)
    logger.info("Scheduled notify_created for meeting %s", meeting_id)

    now = datetime.now(timezone.utc)
    if scheduled_utc:
        reminder_eta = scheduled_utc - timedelta(minutes=5)
        if reminder_eta > now:
            notify_meeting_reminder.apply_async(args=[meeting_id], eta=reminder_eta)
            logger.info(
                "Scheduled reminder for meeting %s at %s", meeting_id, reminder_eta
            )

    # New trigger system
    try:
        from src.models.trigger import TriggerType
        from src.services.events.dispatcher import EventDispatcher

        await EventDispatcher.emit(
            TriggerType.meeting_created,
            {
                "meeting_id": meeting_id,
                "mentor_id": mentor_id,
                "student_id": student_id,
                "scheduled_at": scheduled_utc.isoformat() if scheduled_utc else None,
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to emit meeting_created event for meeting %s: %s", meeting_id, exc
        )


async def _finalize_meeting(
    user_id: int, state: FSMContext, link: str | None, reply_func
):
    data = await state.get_data()

    student_id = data.get("student_id")
    description = data.get("description")
    event_type = data.get("event_type")
    scheduled_at_raw = data.get("scheduled_at")
    scheduled_at = None
    if scheduled_at_raw:
        scheduled_at = _parse_datetime(scheduled_at_raw)

    if not scheduled_at:
        await reply_func(
            "Не удалось сохранить дату/время. Попробуйте создать созвон заново.",
            reply_markup=await _menu_kb(user_id),
        )
        await state.clear()
        return

    # Resolve student username for Notion sync
    mentee_tag = None
    if student_id:
        student = await UserDAO.find_one_or_none(telegram_id=student_id)
        if student and student.username:
            mentee_tag = f"@{student.username}"
    if not mentee_tag:
        mentee_id = data.get("mentee_id")
        if mentee_id:
            mentee = await MenteeDAO.find_one_or_none(id=mentee_id)
            if mentee and mentee.doc_name:
                mentee_tag = mentee.doc_name

    meeting = await MeetingDAO.create_with_participants(
        description=description,
        meeting_link=link,
        scheduled_at=scheduled_at,
        mentor_id=user_id,
        student_id=student_id,
        topic=description,
        event_type=event_type,
        mentee_telegram_tag=mentee_tag,
    )
    await _schedule_meeting_tasks(meeting, mentor_id=user_id, student_id=student_id)
    await state.clear()

    await reply_func(
        "Созвон успешно создан.",
        reply_markup=await _menu_kb(user_id),
    )


@router.message(
    PermissionFilter("manage_meetings"), StateFilter(CreateMeetingFSM.waiting_link)
)
async def msg_meeting_link(message: Message, state: FSMContext):
    link = message.text.strip() if message.text else ""
    await _finalize_meeting(
        user_id=message.from_user.id,
        state=state,
        link=link or None,
        reply_func=message.answer,
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.waiting_link),
    F.data == "meeting_skip_link",
)
async def cb_meeting_skip_link(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _finalize_meeting(
        user_id=callback.from_user.id,
        state=state,
        link=None,
        reply_func=callback.message.edit_text,
    )


@router.callback_query(PermissionFilter("manage_meetings"), DeleteMeetingCB.filter())
async def cb_delete_meeting(callback: CallbackQuery, callback_data: DeleteMeetingCB):
    await callback.answer()

    deleted, notion_page_id = await MeetingDAO.delete_for_mentor(
        meeting_id=callback_data.meeting_id,
        mentor_id=callback.from_user.id,
    )

    if not deleted:
        await callback.message.edit_text(
            "Созвон не найден или у вас нет прав на удаление.",
            reply_markup=mentor_meetings_keyboard(),
        )
        return

    if notion_page_id:
        from src.tasks.meeting import archive_notion_page

        archive_notion_page.delay(notion_page_id)

    meetings = await MeetingDAO.get_for_user(callback.from_user.id)
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    text = _format_meetings(
        meetings,
        callback.from_user.id,
        viewer_is_mentor=True,
        mentor_tg_ids=mentor_tg_ids,
    )
    await callback.message.edit_text(
        f"Созвон #{callback_data.meeting_id} удалён.\n\n{text}",
        reply_markup=mentor_meetings_keyboard(meetings),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(
        CreateMeetingFSM.choosing_student,
        CreateMeetingFSM.choosing_type,
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
        reply_markup=await _menu_kb(callback.from_user.id),
    )


# Pagination: students list
@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_student),
    PageNavCB.filter(F.menu == "students"),
)
async def cb_students_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=meeting_students_keyboard(mentees, page=callback_data.page)
    )


# Pagination: meetings list
@router.callback_query(
    PermissionFilter("manage_meetings"),
    PageNavCB.filter(F.menu == "meetings"),
)
async def cb_meetings_page(callback: CallbackQuery, callback_data: PageNavCB):
    await callback.answer()
    meetings = await MeetingDAO.get_for_user(callback.from_user.id)
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    text = _format_meetings(
        meetings,
        callback.from_user.id,
        viewer_is_mentor=True,
        mentor_tg_ids=mentor_tg_ids,
    )
    await callback.message.edit_text(
        text, reply_markup=mentor_meetings_keyboard(meetings, page=callback_data.page)
    )
