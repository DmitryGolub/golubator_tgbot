from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import calendar
from datetime import date

from src.bot.callbacks.meeting import (
    ChooseMeetingStudentCB,
    DeleteMeetingCB,
    StartMeetingCallCB,
    ChooseMeetingDateCB,
    NavigateMeetingMonthCB,
    ChooseMeetingTimeCB,
)
from src.bot.keyboards.pagination import get_page_slice, paginate_buttons
from src.models.meeting import Meeting


def mentor_meetings_keyboard(
    meetings: list[Meeting] | None = None,
    page: int = 0,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # Dynamic meeting buttons for pagination
    dynamic_buttons: list[tuple[str, str]] = []
    if meetings:
        for meeting in meetings:
            if meeting.completed_at is None:
                dynamic_buttons.append(
                    (
                        f"Начать созвон #{meeting.id}",
                        StartMeetingCallCB(meeting_id=meeting.id).pack(),
                    )
                )
            dynamic_buttons.append(
                (
                    f"Удалить созвон #{meeting.id}",
                    DeleteMeetingCB(meeting_id=meeting.id).pack(),
                )
            )

    page_items, total_pages = get_page_slice(dynamic_buttons, page)

    nav = paginate_buttons("meetings", page, total_pages)
    if nav:
        kb.row(*nav)

    kb.row(InlineKeyboardButton(text="Добавить созвон", callback_data="meeting_create"))
    kb.row(
        InlineKeyboardButton(
            text="Завершить активный созвон", callback_data="mentor_end_call"
        )
    )
    kb.row(InlineKeyboardButton(text="Заполнить фидбек", callback_data="menu_surveys"))

    for text, cb_data in page_items:
        kb.row(InlineKeyboardButton(text=text, callback_data=cb_data))

    kb.row(InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="back_to_menu"))
    return kb.as_markup()


def meeting_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="meeting_create_cancel")
    kb.adjust(1)
    return kb.as_markup()


def meeting_skip_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏩ Пропустить", callback_data="meeting_skip_link")
    kb.button(text="❌ Отмена", callback_data="meeting_create_cancel")
    kb.adjust(1)
    return kb.as_markup()


def meeting_students_keyboard(students, page: int = 0) -> InlineKeyboardMarkup:
    """Accept User or Mentee objects. Uses doc_name/name and telegram_id."""
    page_items, total_pages = get_page_slice(list(students), page)
    kb = InlineKeyboardBuilder()

    nav = paginate_buttons("students", page, total_pages)
    if nav:
        kb.row(*nav)

    for student in page_items:
        display_name = getattr(student, "doc_name", None) or student.name
        username = getattr(student, "username", None)
        if not username and hasattr(student, "user") and student.user:
            username = student.user.username
        label = f"{display_name} @{username}" if username else display_name
        kb.row(
            InlineKeyboardButton(
                text=label,
                callback_data=ChooseMeetingStudentCB(mentee_id=student.id).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="meeting_create_cancel")
    )
    return kb.as_markup()


def meeting_calendar_keyboard(current: date) -> InlineKeyboardMarkup:
    year = current.year
    month = current.month

    builder = InlineKeyboardBuilder()

    # nav row
    builder.row(
        InlineKeyboardButton(
            text="<==",
            callback_data=NavigateMeetingMonthCB(
                year=year, month=month, delta=-1
            ).pack(),
        ),
        InlineKeyboardButton(text=current.strftime("%B %Y"), callback_data="noop"),
        InlineKeyboardButton(
            text="==>",
            callback_data=NavigateMeetingMonthCB(
                year=year, month=month, delta=1
            ).pack(),
        ),
    )

    # weekdays header
    builder.row(
        *[
            InlineKeyboardButton(text=day_name, callback_data="noop")
            for day_name in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        ]
    )

    # days grid
    month_calendar = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    for week in month_calendar:
        row_buttons: list[InlineKeyboardButton] = []
        for day in week:
            if day == 0:
                row_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            else:
                row_buttons.append(
                    InlineKeyboardButton(
                        text=str(day),
                        callback_data=ChooseMeetingDateCB(
                            year=year, month=month, day=day
                        ).pack(),
                    )
                )
        builder.row(*row_buttons)

    # cancel row
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="meeting_create_cancel")
    )

    return builder.as_markup()


def meeting_time_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    times = ["1000", "1400", "1800", "2000"]
    for i in range(0, len(times), 2):
        pair = times[i : i + 2]
        builder.row(
            *[
                InlineKeyboardButton(
                    text=f"{t[:2]}:{t[2:]}",
                    callback_data=ChooseMeetingTimeCB(t=t).pack(),
                )
                for t in pair
            ]
        )

    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="meeting_create_cancel")
    )
    return builder.as_markup()
