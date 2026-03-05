import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import SQLAlchemyError

from src.bot.callbacks.mentor_feedback import (
    ChooseFeedbackDurationCB,
    ChooseFeedbackMeetingCB,
    ChooseFeedbackStatusCB,
)
from src.bot.filters.role import RoleFilter
from src.bot.keyboards.mentor_feedback import (
    mentor_feedback_cancel_keyboard,
    mentor_feedback_duration_keyboard,
    mentor_feedback_meetings_keyboard,
    mentor_feedback_status_keyboard,
)
from src.bot.keyboards.menu import menu_keyboard
from src.bot.states.mentor_feedback import MentorFeedbackFSM
from src.dao.meeting import MeetingDAO
from src.dao.mentor_feedback import MentorFeedbackDAO
from src.mentor_feedback.constants import (
    MentorFeedbackDuration,
    MentorFeedbackStatus,
)
from src.mentor_feedback.dto import MentorFeedbackCreateData
from src.mentor_feedback.errors import (
    CallNotFoundError,
    MentorFeedbackAlreadyExistsError,
    MentorNotInCallError,
)
from src.models.meeting import Meeting
from src.models.user import Role
from src.services.mentor_feedback import MentorFeedbackService


logger = logging.getLogger(__name__)
router = Router(name="mentor-feedback")
router.message.filter(RoleFilter([Role.mentor]))
router.callback_query.filter(RoleFilter([Role.mentor]))
MOSCOW_TZ = timezone(timedelta(hours=3))


def _to_utc_assuming_msk(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MOSCOW_TZ)
    return dt.astimezone(timezone.utc)


def _is_completed_meeting(meeting: Meeting) -> bool:
    scheduled_utc = _to_utc_assuming_msk(meeting.scheduled_at)
    if scheduled_utc is None:
        return False
    return scheduled_utc <= datetime.now(timezone.utc)


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
        call_id = int(data["meeting_id"])
        payload = MentorFeedbackCreateData(
            status=MentorFeedbackStatus(data["status"]),
            duration=MentorFeedbackDuration(data["duration"]),
            motivation=int(data["motivation"]),
            neuromutation_stage=int(data["neuromutation_stage"]),
            comment=comment,
        )
    except (KeyError, TypeError, ValueError):
        await state.clear()
        return "Сценарий фидбека устарел. Запустите его заново."

    service = MentorFeedbackService()

    try:
        await service.create_feedback(
            call_id=call_id,
            mentor_id=mentor_id,
            payload=payload,
        )
    except CallNotFoundError:
        text = "Созвон не найден. Возможно, он был удален."
    except MentorNotInCallError:
        text = "Не удалось подтвердить доступ к этому созвону."
    except MentorFeedbackAlreadyExistsError:
        text = "Фидбек для этого созвона уже сохранен."
    except SQLAlchemyError:
        logger.exception(
            "Failed to save mentor feedback via bot: mentor_id=%s call_id=%s",
            mentor_id,
            call_id,
        )
        text = "Не удалось сохранить фидбек. Попробуйте позже."
    else:
        text = "Фидбек сохранен."

    await state.clear()
    return text


@router.callback_query(
    RoleFilter([Role.mentor]),
    F.data == "mentor_feedback_start",
)
async def cb_mentor_feedback_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    meetings = await _get_feedback_candidates(callback.from_user.id)
    if not meetings:
        await callback.message.edit_text(
            "Нет завершенных созвонов без фидбека.",
            reply_markup=menu_keyboard(Role.mentor),
        )
        return

    await state.set_state(MentorFeedbackFSM.choosing_meeting)
    await callback.message.edit_text(
        "Выберите созвон, по которому хотите оставить фидбек:",
        reply_markup=mentor_feedback_meetings_keyboard(meetings),
    )


@router.callback_query(
    RoleFilter([Role.mentor]),
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
    RoleFilter([Role.mentor]),
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
            reply_markup=menu_keyboard(Role.mentor),
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
    RoleFilter([Role.mentor]),
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
            reply_markup=menu_keyboard(Role.mentor),
        )
        await state.clear()
        return

    await state.update_data(duration=duration.value)
    await state.set_state(MentorFeedbackFSM.waiting_motivation)

    await callback.message.edit_text(
        "Оцените мотивацию ученика по шкале от 1 до 5:",
        reply_markup=mentor_feedback_cancel_keyboard(),
    )


@router.message(
    RoleFilter([Role.mentor]),
    StateFilter(MentorFeedbackFSM.waiting_motivation),
)
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
    RoleFilter([Role.mentor]),
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


@router.message(
    RoleFilter([Role.mentor]),
    StateFilter(MentorFeedbackFSM.waiting_comment),
)
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
    await message.answer(text, reply_markup=menu_keyboard(Role.mentor))


@router.callback_query(
    RoleFilter([Role.mentor]),
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
    await callback.message.edit_text(text, reply_markup=menu_keyboard(Role.mentor))


@router.callback_query(
    RoleFilter([Role.mentor]),
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
        reply_markup=menu_keyboard(Role.mentor),
    )
