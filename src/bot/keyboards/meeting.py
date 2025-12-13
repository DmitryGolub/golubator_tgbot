from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import calendar
from datetime import date

from src.bot.callbacks.meeting import (
    ChooseMeetingStudentCB,
    DeleteMeetingCB,
    ChooseMeetingDateCB,
    NavigateMeetingMonthCB,
    ChooseMeetingTimeCB,
)
from src.models.user import User
from src.models.meeting import Meeting


def mentor_meetings_keyboard(meetings: list[Meeting] | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Добавить созвон", callback_data="meeting_create")

    if meetings:
        for meeting in meetings:
            kb.button(
                text=f"Удалить созвон #{meeting.id}",
                callback_data=DeleteMeetingCB(meeting_id=meeting.id).pack(),
            )

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def meeting_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="meeting_create_cancel")
    kb.adjust(1)
    return kb.as_markup()


def meeting_students_keyboard(students: list[User]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for student in students:
        kb.button(
            text=f"{student.name} @{student.username}",
            callback_data=ChooseMeetingStudentCB(student_id=student.telegram_id).pack(),
        )

    kb.button(text="❌ Отмена", callback_data="meeting_create_cancel")
    kb.adjust(1)
    return kb.as_markup()


def meeting_calendar_keyboard(current: date) -> InlineKeyboardMarkup:
    year = current.year
    month = current.month

    builder = InlineKeyboardBuilder()

    # nav row
    builder.row(
        InlineKeyboardButton(
            text="<==",
            callback_data=NavigateMeetingMonthCB(year=year, month=month, delta=-1).pack(),
        ),
        InlineKeyboardButton(text=current.strftime("%B %Y"), callback_data="noop"),
        InlineKeyboardButton(
            text="==>",
            callback_data=NavigateMeetingMonthCB(year=year, month=month, delta=1).pack(),
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
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="meeting_create_cancel"))

    return builder.as_markup()


def meeting_time_keyboard(date_str: str) -> InlineKeyboardMarkup:
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

    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="meeting_create_cancel"))
    return builder.as_markup()
