import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks.survey import (
    StartSurveyCB,
    SurveyCommentSkipCB,
    SurveyDurationCB,
    SurveyRatingCB,
)
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import menu_keyboard
from src.bot.keyboards.survey import (
    survey_comment_keyboard,
    survey_duration_keyboard,
    survey_rating_keyboard,
)
from src.bot.states.survey import SurveyFSM
from src.services.auth import AuthService
from src.services.survey import (
    CallNotFoundError,
    SurveyAccessDeniedError,
    SurveyNotAvailableError,
    SurveyService,
    SurveyStudentNotFoundError,
)
from src.survey.constants import DURATION_OPTION_LABELS, DurationOption
from src.survey.schemas import SurveyStatus, SurveySubmitRequest

router = Router(name="survey")
router.message.filter(PermissionFilter("fill_survey"))
router.callback_query.filter(PermissionFilter("fill_survey"))

QUESTION_MENTOR = "mentor"
QUESTION_KNOWLEDGE = "knowledge"
QUESTION_UNDERSTANDING = "understanding"


async def _menu_kb(user_id: int):
    perms = await AuthService.get_user_permissions(user_id)
    return menu_keyboard(perms)


def _duration_label(value: str) -> str:
    for option, label in DURATION_OPTION_LABELS.items():
        if option.value == value:
            return label
    return value


def _format_completed_response(call_id: int, response: object) -> str:
    duration = _duration_label(getattr(response, "duration_option", "—"))
    mentor_style = getattr(response, "mentor_style", "—")
    knowledge_depth = getattr(response, "knowledge_depth", "—")
    understanding = getattr(response, "understanding", "—")
    comment = getattr(response, "comment", None) or "—"
    return (
        f"Опрос по созвону #{call_id} уже заполнен.\n\n"
        f"Длительность: <b>{duration}</b>\n"
        f"Стиль общения ментора: <b>{mentor_style}</b>\n"
        f"Глубина проверки знаний: <b>{knowledge_depth}</b>\n"
        f"Понимание материала: <b>{understanding}</b>\n"
        f"Комментарий: {comment}"
    )


async def _send_message(
    message: Message,
    text: str,
    *,
    reply_markup=None,
    edit: bool = False,
) -> None:
    if edit:
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            raise
    await message.answer(text, reply_markup=reply_markup)


async def _start_survey(
    message: Message,
    state: FSMContext,
    *,
    student_id: int,
    call_id: int,
    edit: bool = False,
) -> None:
    service = SurveyService()
    try:
        survey_state, response = await service.get_survey_state_for_student(
            call_id=call_id,
            student_id=student_id,
        )
    except CallNotFoundError:
        await _send_message(message, f"Созвон #{call_id} не найден.", edit=edit)
        return
    except SurveyAccessDeniedError:
        await _send_message(message, "Этот опрос доступен только ученику данного созвона.", edit=edit)
        return
    except SurveyStudentNotFoundError:
        await _send_message(
            message,
            "Не удалось определить ученика для этого созвона.",
            edit=edit,
        )
        return

    if survey_state == SurveyStatus.not_available:
        await _send_message(
            message,
            "Опрос станет доступен после завершения созвона.",
            edit=edit,
        )
        return

    if survey_state == SurveyStatus.completed and response:
        await state.clear()
        await _send_message(message, _format_completed_response(call_id, response), edit=edit)
        return

    await state.clear()
    await state.set_state(SurveyFSM.choosing_duration)
    await state.update_data(call_id=call_id)
    await _send_message(
        message,
        (
            f"Опрос по созвону #{call_id}\n\n"
            "1/5. Какая была длительность созвона?"
        ),
        reply_markup=survey_duration_keyboard(call_id),
        edit=edit,
    )


async def _submit_survey(
    message: Message,
    state: FSMContext,
    *,
    student_id: int,
    comment: str | None,
    edit: bool = False,
) -> None:
    data = await state.get_data()
    call_id = data.get("call_id")
    duration_option = data.get("duration_option")
    mentor_style = data.get("mentor_style")
    knowledge_depth = data.get("knowledge_depth")
    understanding = data.get("understanding")

    if not all([call_id, duration_option, mentor_style, knowledge_depth, understanding]):
        await state.clear()
        await _send_message(
            message,
            "Сессия опроса устарела. Запустите заново: /survey <id_созвона>.",
            reply_markup=await _menu_kb(student_id),
            edit=edit,
        )
        return

    try:
        payload = SurveySubmitRequest(
            duration_option=DurationOption(duration_option),
            mentor_style=mentor_style,
            knowledge_depth=knowledge_depth,
            understanding=understanding,
            comment=comment,
        )
    except ValueError:
        await state.clear()
        await _send_message(
            message,
            "Не удалось разобрать данные опроса. Запустите заново: /survey <id_созвона>.",
            reply_markup=await _menu_kb(student_id),
            edit=edit,
        )
        return

    service = SurveyService()
    try:
        _, already_submitted = await service.submit_survey_for_student(
            call_id=call_id,
            student_id=student_id,
            payload=payload,
        )
    except CallNotFoundError:
        await state.clear()
        await _send_message(message, f"Созвон #{call_id} не найден.", edit=edit)
        return
    except SurveyNotAvailableError:
        await state.clear()
        await _send_message(
            message,
            "Опрос доступен только после завершения созвона.",
            edit=edit,
        )
        return
    except SurveyAccessDeniedError:
        await state.clear()
        await _send_message(message, "Этот опрос доступен только ученику данного созвона.", edit=edit)
        return
    except SurveyStudentNotFoundError:
        await state.clear()
        await _send_message(
            message,
            "Не удалось определить ученика для этого созвона.",
            edit=edit,
        )
        return

    await state.clear()
    if already_submitted:
        text = f"Опрос по созвону #{call_id} уже был заполнен ранее."
    else:
        text = f"Спасибо! Опрос по созвону #{call_id} сохранён."

    await _send_message(
        message,
        text,
        reply_markup=await _menu_kb(student_id),
        edit=edit,
    )


async def _check_call_id(state: FSMContext, call_id: int) -> bool:
    data = await state.get_data()
    return data.get("call_id") == call_id


@router.message(Command("survey"))
async def cmd_survey(message: Message, state: FSMContext, command: CommandObject):
    raw_args = (command.args or "").strip()
    if not raw_args or not raw_args.isdigit():
        await message.answer(
            "Формат команды: /survey <id_созвона>\n"
            "Пример: /survey 123",
        )
        return

    await _start_survey(
        message,
        state,
        student_id=message.from_user.id,
        call_id=int(raw_args),
        edit=False,
    )


@router.message(F.text.regexp(r"^/survey_(\d+)$"))
async def cmd_survey_with_suffix(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    match = re.match(r"^/survey_(\d+)$", text)
    if not match:
        return
    await _start_survey(
        message,
        state,
        student_id=message.from_user.id,
        call_id=int(match.group(1)),
        edit=False,
    )


@router.callback_query(StartSurveyCB.filter())
async def cb_survey_start(callback: CallbackQuery, callback_data: StartSurveyCB, state: FSMContext):
    await callback.answer()
    await _start_survey(
        callback.message,
        state,
        student_id=callback.from_user.id,
        call_id=callback_data.call_id,
        edit=True,
    )


@router.callback_query(
    StateFilter(SurveyFSM.choosing_duration),
    SurveyDurationCB.filter(),
)
async def cb_survey_duration(
    callback: CallbackQuery,
    callback_data: SurveyDurationCB,
    state: FSMContext,
):
    if not await _check_call_id(state, callback_data.call_id):
        await callback.answer("Эта кнопка больше неактуальна.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(duration_option=callback_data.option)
    await state.set_state(SurveyFSM.rating_mentor_style)
    await callback.message.edit_text(
        "2/5. Оцените стиль общения ментора (1-5):",
        reply_markup=survey_rating_keyboard(callback_data.call_id, QUESTION_MENTOR),
    )


@router.callback_query(
    StateFilter(SurveyFSM.rating_mentor_style),
    SurveyRatingCB.filter(),
)
async def cb_survey_mentor_style(
    callback: CallbackQuery,
    callback_data: SurveyRatingCB,
    state: FSMContext,
):
    if callback_data.question != QUESTION_MENTOR:
        await callback.answer("Выберите оценку для текущего вопроса.", show_alert=True)
        return
    if not await _check_call_id(state, callback_data.call_id):
        await callback.answer("Эта кнопка больше неактуальна.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(mentor_style=callback_data.value)
    await state.set_state(SurveyFSM.rating_knowledge_depth)
    await callback.message.edit_text(
        "3/5. Оцените глубину проверки знаний (1-5):",
        reply_markup=survey_rating_keyboard(callback_data.call_id, QUESTION_KNOWLEDGE),
    )


@router.callback_query(
    StateFilter(SurveyFSM.rating_knowledge_depth),
    SurveyRatingCB.filter(),
)
async def cb_survey_knowledge_depth(
    callback: CallbackQuery,
    callback_data: SurveyRatingCB,
    state: FSMContext,
):
    if callback_data.question != QUESTION_KNOWLEDGE:
        await callback.answer("Выберите оценку для текущего вопроса.", show_alert=True)
        return
    if not await _check_call_id(state, callback_data.call_id):
        await callback.answer("Эта кнопка больше неактуальна.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(knowledge_depth=callback_data.value)
    await state.set_state(SurveyFSM.rating_understanding)
    await callback.message.edit_text(
        "4/5. Насколько вы поняли материал на созвоне? (1-5):",
        reply_markup=survey_rating_keyboard(callback_data.call_id, QUESTION_UNDERSTANDING),
    )


@router.callback_query(
    StateFilter(SurveyFSM.rating_understanding),
    SurveyRatingCB.filter(),
)
async def cb_survey_understanding(
    callback: CallbackQuery,
    callback_data: SurveyRatingCB,
    state: FSMContext,
):
    if callback_data.question != QUESTION_UNDERSTANDING:
        await callback.answer("Выберите оценку для текущего вопроса.", show_alert=True)
        return
    if not await _check_call_id(state, callback_data.call_id):
        await callback.answer("Эта кнопка больше неактуальна.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(understanding=callback_data.value)
    await state.set_state(SurveyFSM.waiting_comment)
    await callback.message.edit_text(
        "5/5. Добавьте комментарий одним сообщением или пропустите:",
        reply_markup=survey_comment_keyboard(callback_data.call_id),
    )


@router.callback_query(
    StateFilter(SurveyFSM.waiting_comment),
    SurveyCommentSkipCB.filter(),
)
async def cb_survey_skip_comment(
    callback: CallbackQuery,
    callback_data: SurveyCommentSkipCB,
    state: FSMContext,
):
    if not await _check_call_id(state, callback_data.call_id):
        await callback.answer("Эта кнопка больше неактуальна.", show_alert=True)
        return

    await callback.answer()
    await _submit_survey(
        callback.message,
        state,
        student_id=callback.from_user.id,
        comment=None,
        edit=True,
    )


@router.message(StateFilter(SurveyFSM.waiting_comment))
async def msg_survey_comment(message: Message, state: FSMContext):
    comment = (message.text or "").strip() or None
    await _submit_survey(
        message,
        state,
        student_id=message.from_user.id,
        comment=comment,
        edit=False,
    )


@router.callback_query(
    StateFilter(
        SurveyFSM.choosing_duration,
        SurveyFSM.rating_mentor_style,
        SurveyFSM.rating_knowledge_depth,
        SurveyFSM.rating_understanding,
        SurveyFSM.waiting_comment,
    ),
    F.data == "survey_cancel",
)
async def cb_survey_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "Опрос отменён.",
        reply_markup=await _menu_kb(callback.from_user.id),
    )
