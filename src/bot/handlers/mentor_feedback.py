import logging
from enum import StrEnum

from aiogram import F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import menu_keyboard
from src.dao.meeting import MeetingDAO
from src.dao.mentor_feedback import MentorFeedbackDAO
from src.models.meeting import Meeting
from src.services.auth import AuthService
from src.utils.roles import is_student, is_mentor


logger = logging.getLogger(__name__)
router = Router(name="mentor-feedback")
router.message.filter(PermissionFilter("give_feedback"))
router.callback_query.filter(PermissionFilter("give_feedback"))


class MentorFeedbackStatus(StrEnum):
    not_ready = "not_ready"
    bad = "bad"
    ok = "ok"
    great = "great"


class MentorFeedbackDuration(StrEnum):
    lt_30 = "lt_30"
    min_30_60 = "min_30_60"
    min_60_90 = "min_60_90"
    ge_90 = "ge_90"


class MentorFeedbackFSM(StatesGroup):
    choosing_meeting = State()
    choosing_status = State()
    choosing_duration = State()
    waiting_motivation = State()
    waiting_neuromutation_stage = State()
    waiting_comment = State()


class ChooseFeedbackMeetingCB(CallbackData, prefix="feedback_meeting"):
    meeting_id: int


class ChooseFeedbackStatusCB(CallbackData, prefix="feedback_status"):
    value: str


class ChooseFeedbackDurationCB(CallbackData, prefix="feedback_duration"):
    value: str


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


async def _menu_kb(user_id: int):
    perms = await AuthService.get_user_permissions(user_id)
    return menu_keyboard(perms)


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
    when = meeting.scheduled_at.strftime("%d.%m %H:%M") if meeting.scheduled_at else "без даты"
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


def _is_completed_meeting(meeting: Meeting) -> bool:
    return meeting.completed_at is not None


async def _get_feedback_candidates(mentor_id: int) -> list[Meeting]:
    meetings = await MeetingDAO.get_for_user(mentor_id)
    completed_meetings = [
        meeting
        for meeting in meetings
        if _is_completed_meeting(meeting)
    ]

    if not completed_meetings:
        return []

    feedback_call_ids = await MentorFeedbackDAO.get_call_ids(
        [meeting.id for meeting in completed_meetings]
    )
    return [
        meeting
        for meeting in completed_meetings
        if meeting.id not in feedback_call_ids
    ]


def _parse_score(value: str | None, *, min_value: int, max_value: int) -> int | None:
    raw = (value or "").strip()
    if not raw.isdigit():
        return None

    parsed = int(raw)
    if min_value <= parsed <= max_value:
        return parsed
    return None


async def _submit_feedback(
    *,
    mentor_id: int,
    state: FSMContext,
    comment: str | None,
) -> str:
    data = await state.get_data()

    try:
        meeting_id = int(data["meeting_id"])
        status = MentorFeedbackStatus(data["status"])
        duration = MentorFeedbackDuration(data["duration"])
        motivation = int(data["motivation"])
        neuromutation_stage = int(data["neuromutation_stage"])
    except (KeyError, TypeError, ValueError):
        await state.clear()
        return "Сценарий фидбека устарел. Запустите его заново."

    meeting = await MeetingDAO.get_with_participants(meeting_id)
    if not meeting:
        await state.clear()
        return "Созвон не найден. Возможно, он был удален."

    mentor = next(
        (
            participant
            for participant in meeting.participants
            if participant.telegram_id == mentor_id and is_mentor(participant)
        ),
        None,
    )
    if not mentor:
        await state.clear()
        return "Не удалось подтвердить доступ к этому созвону."

    if await MentorFeedbackDAO.get_by_call_id(meeting_id):
        await state.clear()
        return "Фидбек для этого созвона уже сохранен."

    try:
        await MentorFeedbackDAO.create(
            call_id=meeting_id,
            mentor_id=mentor_id,
            status=status.value,
            duration=duration.value,
            motivation=motivation,
            neuromutation_stage=neuromutation_stage,
            comment=comment,
        )
    except IntegrityError:
        text = "Фидбек для этого созвона уже сохранен."
    except SQLAlchemyError:
        logger.exception(
            "Failed to save mentor feedback via bot: mentor_id=%s meeting_id=%s",
            mentor_id,
            meeting_id,
        )
        text = "Не удалось сохранить фидбек. Попробуйте позже."
    else:
        text = "Фидбек сохранен."

    await state.clear()
    return text


@router.callback_query(F.data == "mentor_feedback_start")
async def cb_mentor_feedback_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    meetings = await _get_feedback_candidates(callback.from_user.id)
    if not meetings:
        await callback.message.edit_text(
            "Нет завершенных созвонов без фидбека.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        return

    await state.set_state(MentorFeedbackFSM.choosing_meeting)
    await callback.message.edit_text(
        "Выберите созвон, по которому хотите оставить фидбек:",
        reply_markup=mentor_feedback_meetings_keyboard(meetings),
    )


@router.callback_query(
    StateFilter(MentorFeedbackFSM.choosing_meeting),
    ChooseFeedbackMeetingCB.filter(),
)
async def cb_choose_feedback_meeting(
    callback: CallbackQuery,
    callback_data: ChooseFeedbackMeetingCB,
    state: FSMContext,
):
    await callback.answer()
    await state.update_data(meeting_id=callback_data.meeting_id)
    await state.set_state(MentorFeedbackFSM.choosing_status)

    await callback.message.edit_text(
        "Как прошел созвон?",
        reply_markup=mentor_feedback_status_keyboard(),
    )


@router.callback_query(
    StateFilter(MentorFeedbackFSM.choosing_status),
    ChooseFeedbackStatusCB.filter(),
)
async def cb_choose_feedback_status(
    callback: CallbackQuery,
    callback_data: ChooseFeedbackStatusCB,
    state: FSMContext,
):
    await callback.answer()

    try:
        status = MentorFeedbackStatus(callback_data.value)
    except ValueError:
        await callback.message.edit_text(
            "Не удалось распознать статус. Начните заново.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        await state.clear()
        return

    await state.update_data(status=status.value)
    await state.set_state(MentorFeedbackFSM.choosing_duration)

    await callback.message.edit_text(
        "Сколько длился созвон?",
        reply_markup=mentor_feedback_duration_keyboard(),
    )


@router.callback_query(
    StateFilter(MentorFeedbackFSM.choosing_duration),
    ChooseFeedbackDurationCB.filter(),
)
async def cb_choose_feedback_duration(
    callback: CallbackQuery,
    callback_data: ChooseFeedbackDurationCB,
    state: FSMContext,
):
    await callback.answer()

    try:
        duration = MentorFeedbackDuration(callback_data.value)
    except ValueError:
        await callback.message.edit_text(
            "Не удалось распознать длительность. Начните заново.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        await state.clear()
        return

    await state.update_data(duration=duration.value)
    await state.set_state(MentorFeedbackFSM.waiting_motivation)

    await callback.message.edit_text(
        "Оцените мотивацию ученика по шкале от 1 до 5:",
        reply_markup=mentor_feedback_cancel_keyboard(),
    )


@router.message(StateFilter(MentorFeedbackFSM.waiting_motivation))
async def msg_feedback_motivation(message: Message, state: FSMContext):
    motivation = _parse_score(message.text, min_value=1, max_value=5)
    if motivation is None:
        await message.answer(
            "Нужно число от 1 до 5.",
            reply_markup=mentor_feedback_cancel_keyboard(),
        )
        return

    await state.update_data(motivation=motivation)
    await state.set_state(MentorFeedbackFSM.waiting_neuromutation_stage)
    await message.answer(
        "Укажите стадию нейромутации от 1 до 10:",
        reply_markup=mentor_feedback_cancel_keyboard(),
    )


@router.message(
    StateFilter(MentorFeedbackFSM.waiting_neuromutation_stage),
)
async def msg_feedback_neuromutation_stage(message: Message, state: FSMContext):
    stage = _parse_score(message.text, min_value=1, max_value=10)
    if stage is None:
        await message.answer(
            "Нужно число от 1 до 10.",
            reply_markup=mentor_feedback_cancel_keyboard(),
        )
        return

    await state.update_data(neuromutation_stage=stage)
    await state.set_state(MentorFeedbackFSM.waiting_comment)
    await message.answer(
        "Добавьте комментарий к созвону или пропустите этот шаг:",
        reply_markup=mentor_feedback_cancel_keyboard(allow_skip_comment=True),
    )


@router.message(StateFilter(MentorFeedbackFSM.waiting_comment))
async def msg_feedback_comment(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "Комментарий нужно отправить текстом или пропустить.",
            reply_markup=mentor_feedback_cancel_keyboard(allow_skip_comment=True),
        )
        return

    text = await _submit_feedback(
        mentor_id=message.from_user.id,
        state=state,
        comment=message.text.strip() or None,
    )
    await message.answer(text, reply_markup=await _menu_kb(message.from_user.id))


@router.callback_query(
    StateFilter(MentorFeedbackFSM.waiting_comment),
    F.data == "mentor_feedback_skip_comment",
)
async def cb_feedback_skip_comment(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    text = await _submit_feedback(
        mentor_id=callback.from_user.id,
        state=state,
        comment=None,
    )
    await callback.message.edit_text(text, reply_markup=await _menu_kb(callback.from_user.id))


@router.callback_query(
    StateFilter(
        MentorFeedbackFSM.choosing_meeting,
        MentorFeedbackFSM.choosing_status,
        MentorFeedbackFSM.choosing_duration,
        MentorFeedbackFSM.waiting_motivation,
        MentorFeedbackFSM.waiting_neuromutation_stage,
        MentorFeedbackFSM.waiting_comment,
    ),
    F.data == "mentor_feedback_cancel",
)
async def cb_feedback_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "Заполнение фидбека отменено.",
        reply_markup=await _menu_kb(callback.from_user.id),
    )
