from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import calendar
from datetime import date

from src.bot.callbacks.meeting import (
    ChooseMeetingStudentCB,
    ChooseMeetingTypeCB,
    ConfirmMeetingCB,
    ConfirmParticipantSelectionCB,
    DeclineMeetingCB,
    DeleteMeetingCB,
    EditMeetingCB,
    EditMeetingFieldCB,
    ProposeNewTimeCB,
    ShowAllUsersCB,
    StartMeetingCallCB,
    ChooseMeetingDateCB,
    NavigateMeetingMonthCB,
    ChooseMeetingTimeCB,
    ToggleMeetingParticipantCB,
)
from src.bot.keyboards.pagination import get_page_slice, paginate_buttons
from src.models.meeting import Meeting, ProposalStatus


MEETINGS_PAGE_SIZE = 5


def pending_meeting_keyboard(meeting_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=ConfirmMeetingCB(meeting_id=meeting_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🔄 Предложить другое время",
            callback_data=ProposeNewTimeCB(meeting_id=meeting_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=DeclineMeetingCB(meeting_id=meeting_id).pack(),
        )
    )
    return kb.as_markup()


def edit_meeting_fields_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📅 Дата и время",
            callback_data=EditMeetingFieldCB(field="datetime").pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="📝 Описание",
            callback_data=EditMeetingFieldCB(field="description").pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🔗 Ссылка",
            callback_data=EditMeetingFieldCB(field="link").pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="📋 Тип встречи",
            callback_data=EditMeetingFieldCB(field="type").pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="👥 Участники",
            callback_data=EditMeetingFieldCB(field="student").pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="meeting_create_cancel")
    )
    return kb.as_markup()


def mentor_meetings_keyboard(
    meetings: list[Meeting] | None = None,
    page: int = 0,
    viewer_id: int | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    page_size = MEETINGS_PAGE_SIZE
    all_meetings = meetings or []
    total_pages = max(1, (len(all_meetings) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_meetings = all_meetings[start : start + page_size]

    nav = paginate_buttons("meetings", page, total_pages)
    if nav:
        kb.row(*nav)

    for local_idx, meeting in enumerate(page_meetings):
        global_idx = start + local_idx + 1
        row: list[InlineKeyboardButton] = []

        is_pending = meeting.proposal_status == ProposalStatus.pending_confirmation
        viewer_is_not_proposer = (
            viewer_id is not None and meeting.proposed_by != viewer_id
        )

        if is_pending and viewer_is_not_proposer:
            # Show proposal action buttons instead of start/delete
            if meeting.original_scheduled_at:
                kb.row(
                    InlineKeyboardButton(
                        text=f"📋 Перенос #{global_idx}",
                        callback_data=ConfirmMeetingCB(meeting_id=meeting.id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="❌",
                        callback_data=DeclineMeetingCB(meeting_id=meeting.id).pack(),
                    ),
                )
            else:
                kb.row(
                    InlineKeyboardButton(
                        text=f"✅ #{global_idx}",
                        callback_data=ConfirmMeetingCB(meeting_id=meeting.id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="🔄",
                        callback_data=ProposeNewTimeCB(meeting_id=meeting.id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="❌",
                        callback_data=DeclineMeetingCB(meeting_id=meeting.id).pack(),
                    ),
                )
            continue

        if meeting.completed_at is None and not is_pending:
            row.append(
                InlineKeyboardButton(
                    text=f"Начать #{global_idx}",
                    callback_data=StartMeetingCallCB(meeting_id=meeting.id).pack(),
                )
            )
            row.append(
                InlineKeyboardButton(
                    text="✏️",
                    callback_data=EditMeetingCB(meeting_id=meeting.id).pack(),
                )
            )
        row.append(
            InlineKeyboardButton(
                text=f"Удалить #{global_idx}",
                callback_data=DeleteMeetingCB(meeting_id=meeting.id).pack(),
            )
        )
        kb.row(*row)

    kb.row(InlineKeyboardButton(text="Добавить созвон", callback_data="meeting_create"))
    kb.row(
        InlineKeyboardButton(
            text="Завершить активный созвон", callback_data="mentor_end_call"
        )
    )
    kb.row(InlineKeyboardButton(text="Заполнить фидбек", callback_data="my_surveys"))
    kb.row(
        InlineKeyboardButton(
            text="📋 Завершённые созвоны", callback_data="past_meetings_mentor"
        )
    )
    kb.row(InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="back_to_menu"))
    return kb.as_markup()


def student_meetings_keyboard(
    meetings: list[Meeting] | None = None,
    page: int = 0,
    viewer_id: int | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    page_size = MEETINGS_PAGE_SIZE
    all_meetings = meetings or []
    total_pages = max(1, (len(all_meetings) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_meetings = all_meetings[start : start + page_size]

    nav = paginate_buttons("meetings", page, total_pages)
    if nav:
        kb.row(*nav)

    for local_idx, meeting in enumerate(page_meetings):
        global_idx = start + local_idx + 1

        is_pending = meeting.proposal_status == ProposalStatus.pending_confirmation
        viewer_is_not_proposer = (
            viewer_id is not None and meeting.proposed_by != viewer_id
        )

        if is_pending and viewer_is_not_proposer:
            if meeting.original_scheduled_at:
                kb.row(
                    InlineKeyboardButton(
                        text=f"📋 Перенос #{global_idx}",
                        callback_data=ConfirmMeetingCB(meeting_id=meeting.id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="❌",
                        callback_data=DeclineMeetingCB(meeting_id=meeting.id).pack(),
                    ),
                )
            else:
                kb.row(
                    InlineKeyboardButton(
                        text=f"✅ #{global_idx}",
                        callback_data=ConfirmMeetingCB(meeting_id=meeting.id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="🔄",
                        callback_data=ProposeNewTimeCB(meeting_id=meeting.id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="❌",
                        callback_data=DeclineMeetingCB(meeting_id=meeting.id).pack(),
                    ),
                )

    kb.row(
        InlineKeyboardButton(
            text="📋 Завершённые созвоны", callback_data="past_meetings_student"
        )
    )
    kb.row(InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="back_to_menu"))
    return kb.as_markup()


def meeting_participants_multiselect_keyboard(
    users: list,
    selected_ids: set[int],
    page: int = 0,
    show_all_button: bool = True,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    page_items, total_pages = get_page_slice(list(users), page)

    nav = paginate_buttons("participants", page, total_pages)
    if nav:
        kb.row(*nav)

    for user in page_items:
        tid = getattr(user, "telegram_id", None)
        if tid is None and hasattr(user, "user") and user.user:
            tid = user.user.telegram_id
        display_name = getattr(user, "doc_name", None) or getattr(user, "name", None)
        if not display_name and hasattr(user, "user") and user.user:
            display_name = user.user.name
        if not display_name:
            display_name = f"id={tid}"
        username = getattr(user, "username", None)
        if not username and hasattr(user, "user") and user.user:
            username = user.user.username
        label = f"{display_name} @{username}" if username else display_name
        prefix = "✓ " if tid in selected_ids else "  "
        kb.row(
            InlineKeyboardButton(
                text=f"{prefix}{label}",
                callback_data=ToggleMeetingParticipantCB(user_id=tid).pack(),
            )
        )

    if show_all_button:
        kb.row(
            InlineKeyboardButton(
                text="🔍 Показать всех пользователей",
                callback_data=ShowAllUsersCB().pack(),
            )
        )

    if selected_ids:
        kb.row(
            InlineKeyboardButton(
                text=f"✅ Готово ({len(selected_ids)})",
                callback_data=ConfirmParticipantSelectionCB().pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="meeting_create_cancel")
    )
    return kb.as_markup()


def meeting_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="meeting_create_cancel")
    kb.adjust(1)
    return kb.as_markup()


def meeting_link_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
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
        display_name = getattr(student, "doc_name", None) or (
            student.user.name if student.user else f"id={student.id}"
        )
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


MEETING_TYPES = [
    "Поиск работы",
    "Синк",
    "1:1",
    "Планирование",
    "Ретро",
    "Интервью",
    "Обучение",
    "Знакомство",
    "Поддержка на ИС",
    "Консультация",
]


def meeting_type_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    buttons: list[tuple[str, str]] = [
        (t, ChooseMeetingTypeCB(type_idx=i).pack()) for i, t in enumerate(MEETING_TYPES)
    ]
    page_items, total_pages = get_page_slice(buttons, page, page_size=5)

    kb = InlineKeyboardBuilder()

    nav = paginate_buttons("meeting_types", page, total_pages)
    if nav:
        kb.row(*nav)

    for text, cb_data in page_items:
        kb.row(InlineKeyboardButton(text=text, callback_data=cb_data))

    kb.row(
        InlineKeyboardButton(text="⏩ Пропустить", callback_data="meeting_skip_type")
    )
    kb.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="meeting_create_cancel")
    )
    return kb.as_markup()


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


def mentor_past_meetings_keyboard(
    meetings: list[Meeting] | None = None,
    page: int = 0,
    viewer_id: int | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    page_size = MEETINGS_PAGE_SIZE
    all_meetings = meetings or []
    total_pages = max(1, (len(all_meetings) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_meetings = all_meetings[start : start + page_size]

    nav = paginate_buttons("past_meetings", page, total_pages)
    if nav:
        kb.row(*nav)

    for local_idx, meeting in enumerate(page_meetings):
        global_idx = start + local_idx + 1
        kb.row(
            InlineKeyboardButton(
                text=f"Удалить #{global_idx}",
                callback_data=DeleteMeetingCB(meeting_id=meeting.id).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text="⬅️ Назад к созвонам", callback_data="mentor_meetings_list"
        )
    )
    return kb.as_markup()


def student_past_meetings_keyboard(
    meetings: list[Meeting] | None = None,
    page: int = 0,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    page_size = MEETINGS_PAGE_SIZE
    all_meetings = meetings or []
    total_pages = max(1, (len(all_meetings) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    nav = paginate_buttons("past_meetings", page, total_pages)
    if nav:
        kb.row(*nav)

    kb.row(
        InlineKeyboardButton(
            text="⬅️ Назад к созвонам", callback_data="student_meetings"
        )
    )
    return kb.as_markup()
