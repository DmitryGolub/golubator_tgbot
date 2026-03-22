from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.mentor_feedback import (
    ChooseFeedbackDurationCB,
    ChooseFeedbackMeetingCB,
    ChooseFeedbackStatusCB,
)
from src.models.meeting import Meeting
from src.utils.roles import is_student
from src.mentor_feedback.constants import (
    MentorFeedbackDuration,
    MentorFeedbackStatus,
)


STATUS_LABELS = {
    MentorFeedbackStatus.not_ready: "Не готов",
    MentorFeedbackStatus.bad: "Плохо",
    MentorFeedbackStatus.ok: "Нормально",
    MentorFeedbackStatus.great: "Отлично",
}

DURATION_LABELS = {
    MentorFeedbackDuration.lt_30: "До 30 минут",
    MentorFeedbackDuration.min_30_60: "30-60 минут",
    MentorFeedbackDuration.min_60_90: "60-90 минут",
    MentorFeedbackDuration.ge_90: "90+ минут",
}


def _meeting_title(meeting: Meeting) -> str:
    student = next(
        (
            participant
            for participant in meeting.participants
            if is_student(participant)
        ),
        None,
    )
    student_name = student.name if student else "ученик"
    when = (
        meeting.scheduled_at.strftime("%d.%m %H:%M")
        if meeting.scheduled_at
        else "без даты"
    )
    return f"Созвон #{meeting.id} • {when} • {student_name}"


def mentor_feedback_meetings_keyboard(meetings: list[Meeting]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for meeting in meetings:
        builder.button(
            text=_meeting_title(meeting),
            callback_data=ChooseFeedbackMeetingCB(meeting_id=meeting.id).pack(),
        )

    builder.button(text="❌ Отмена", callback_data="mentor_feedback_cancel")
    builder.adjust(1)
    return builder.as_markup()


def mentor_feedback_status_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for status in MentorFeedbackStatus:
        builder.button(
            text=STATUS_LABELS[status],
            callback_data=ChooseFeedbackStatusCB(value=status.value).pack(),
        )

    builder.button(text="❌ Отмена", callback_data="mentor_feedback_cancel")
    builder.adjust(1)
    return builder.as_markup()


def mentor_feedback_duration_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for duration in MentorFeedbackDuration:
        builder.button(
            text=DURATION_LABELS[duration],
            callback_data=ChooseFeedbackDurationCB(value=duration.value).pack(),
        )

    builder.button(text="❌ Отмена", callback_data="mentor_feedback_cancel")
    builder.adjust(1)
    return builder.as_markup()


def mentor_feedback_cancel_keyboard(
    *,
    allow_skip_comment: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if allow_skip_comment:
        builder.button(
            text="Пропустить комментарий",
            callback_data="mentor_feedback_skip_comment",
        )

    builder.button(text="❌ Отмена", callback_data="mentor_feedback_cancel")
    builder.adjust(1)
    return builder.as_markup()
