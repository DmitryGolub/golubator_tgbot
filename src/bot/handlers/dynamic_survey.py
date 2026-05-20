import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext

from src.bot.callbacks.dynamic_survey import DynamicSurveyAnswerCB, StartDynamicSurveyCB
from src.bot.handlers.common.menu import render_menu_to
from src.bot.keyboards.dynamic_survey import my_surveys_keyboard
from src.bot.states.dynamic_survey import DynamicSurveyFSM
from src.bot.utils import safe_edit_text
from src.bot.middlewares.survey_block_middleware import (
    invalidate_pending_cache,
    pop_block_message,
)
from src.services.survey_session import (
    SessionAlreadyCompletedError,
    SessionNotFoundError,
    SessionNotOwnedError,
    SurveySessionService,
)

logger = logging.getLogger(__name__)

router = Router(name="dynamic_survey")


async def _cleanup_block_message(
    bot: Bot, user_id: int, current_chat_id: int, current_msg_id: int
) -> None:
    """Drop block-notice message tracked for this user.

    If the tracked message is the one the user is currently interacting with
    (i.e. it's about to be edited into the surveys UI), just forget it.
    Otherwise, delete it from the chat so block notices don't accumulate.
    """
    entry = pop_block_message(user_id)
    if entry is None:
        return
    chat_id, msg_id = entry
    if chat_id == current_chat_id and msg_id == current_msg_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except TelegramBadRequest:
        pass


# --- My surveys list ---


@router.callback_query(lambda c: c.data == "my_surveys")
async def cb_my_surveys(callback: CallbackQuery):
    await _cleanup_block_message(
        callback.bot,
        callback.from_user.id,
        callback.message.chat.id,
        callback.message.message_id,
    )

    service = SurveySessionService()
    sessions = await service.get_available_sessions(callback.from_user.id)

    if not sessions:
        await callback.answer()
        await safe_edit_text(
            callback,
            "Нет доступных опросов.",
            reply_markup=my_surveys_keyboard([]),
        )
        return

    await callback.answer()
    await safe_edit_text(
        callback,
        "Доступные опросы:",
        reply_markup=my_surveys_keyboard(sessions),
    )


# --- Entry point ---


@router.callback_query(StartDynamicSurveyCB.filter())
async def cb_start_survey(
    callback: CallbackQuery, callback_data: StartDynamicSurveyCB, state: FSMContext
):
    from src.dao.survey_session import SurveySessionDAO
    from src.models.survey_template import TemplateKind

    await _cleanup_block_message(
        callback.bot,
        callback.from_user.id,
        callback.message.chat.id,
        callback.message.message_id,
    )

    preview = await SurveySessionDAO.get_by_id(callback_data.session_id)
    if preview and preview.template and preview.template.kind == TemplateKind.broadcast:
        await callback.answer("Это рассылка, не опрос", show_alert=False)
        return

    service = SurveySessionService()

    try:
        session = await service.start_session(
            callback_data.session_id, callback.from_user.id
        )
    except SessionNotFoundError:
        logger.warning("Survey session %s not found", callback_data.session_id)
        await state.clear()
        await callback.answer("Опрос не найден", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        return
    except SessionNotOwnedError:
        await state.clear()
        await callback.answer("Этот опрос не для вас", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        return
    except SessionAlreadyCompletedError:
        await state.clear()
        await callback.answer("Вы уже заполнили этот опрос")
        return

    logger.info("Survey started: session=%s user=%s", session.id, callback.from_user.id)

    questions = await service.get_questions(session.id)
    if not questions:
        await state.clear()
        await callback.answer("В опросе нет вопросов")
        return

    questions_data = [
        {
            "id": q.id,
            "title": q.title,
            "question_type": q.question_type.value,
            "is_required": q.is_required,
            "config": q.config,
            "options": [{"value": o.value, "label": o.label} for o in q.options],
        }
        for q in questions
    ]

    chat_id = callback.message.chat.id
    msg_id = callback.message.message_id

    await state.update_data(
        session_id=session.id,
        respondent_id=callback.from_user.id,
        current_index=0,
        questions=questions_data,
        multi_selected=[],
        survey_chat_id=chat_id,
        survey_msg_id=msg_id,
    )

    await callback.answer()
    await _show_question(
        callback.bot, chat_id, msg_id, state, 0, questions_data, session.template.title
    )


# --- Answer handlers ---


@router.callback_query(
    StateFilter(DynamicSurveyFSM.answering, DynamicSurveyFSM.waiting_text),
    DynamicSurveyAnswerCB.filter(),
)
async def cb_answer(
    callback: CallbackQuery, callback_data: DynamicSurveyAnswerCB, state: FSMContext
):
    value = callback_data.value
    data = await state.get_data()
    chat_id = data.get("survey_chat_id", callback.message.chat.id)
    msg_id = data.get("survey_msg_id", callback.message.message_id)

    if value == "__cancel__":
        respondent_id = data.get("respondent_id", callback.from_user.id)
        await state.clear()
        await callback.answer("Опрос отменён")
        await render_menu_to(
            callback.bot,
            chat_id,
            msg_id,
            respondent_id,
            tg_user=callback.from_user,
            edit=True,
        )
        return

    questions = data["questions"]
    idx = data["current_index"]
    question = questions[idx]

    service = SurveySessionService()

    if question["question_type"] == "multiple_choice":
        if value == "__done__":
            selected = data.get("multi_selected", [])
            if not selected and question["is_required"]:
                await callback.answer("Выберите хотя бы один вариант")
                return

            q_obj = await _load_question(question["id"])
            await service.save_answer(
                session_id=data["session_id"],
                question=q_obj,
                raw_value=selected,
            )
            await state.update_data(multi_selected=[])
            await callback.answer()
            await _advance(callback.bot, chat_id, msg_id, state, data)
            return
        else:
            selected = data.get("multi_selected", [])
            if value in selected:
                selected.remove(value)
            else:
                selected.append(value)
            await state.update_data(multi_selected=selected)

            keyboard = _build_keyboard_from_dict(question, selected=selected)
            try:
                await callback.bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=msg_id, reply_markup=keyboard
                )
            except TelegramBadRequest:
                pass
            await callback.answer(f"Выбрано: {len(selected)}")
            return

    q_obj = await _load_question(question["id"])
    await service.save_answer(
        session_id=data["session_id"],
        question=q_obj,
        raw_value=value,
    )

    await callback.answer()
    await _advance(callback.bot, chat_id, msg_id, state, data)


@router.message(DynamicSurveyFSM.waiting_text)
async def msg_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    idx = data["current_index"]
    question = questions[idx]

    text = message.text.strip() if message.text else ""

    bot = message.bot
    chat_id = data.get("survey_chat_id", message.chat.id)
    msg_id = data.get("survey_msg_id")

    # Delete user input so it doesn't pile up in the chat
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    if not text and question["is_required"]:
        # Re-render the same question as a soft reminder (no new message).
        if msg_id is not None:
            session_service = SurveySessionService()
            session = await session_service.get_session(data["session_id"])
            await _show_question(
                bot, chat_id, msg_id, state, idx, questions, session.template.title
            )
        return

    service = SurveySessionService()
    q_obj = await _load_question(question["id"])
    await service.save_answer(
        session_id=data["session_id"],
        question=q_obj,
        raw_value=text if text else None,
    )

    if msg_id is None:
        # Shouldn't happen — FSM was primed in cb_start_survey. Bail out safely.
        logger.warning("msg_text_answer without survey_msg_id in FSM data")
        await state.clear()
        return

    await _advance(bot, chat_id, msg_id, state, data)


# --- Helpers ---


def _build_keyboard_from_dict(question: dict, selected: list[str] | None = None):
    """Build inline keyboard from question dict stored in FSM data."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from src.bot.callbacks.dynamic_survey import DynamicSurveyAnswerCB

    qtype = question["question_type"]
    builder = InlineKeyboardBuilder()

    if qtype == "rating":
        config = question.get("config") or {}
        min_val = config.get("min", 1)
        max_val = config.get("max", 10)
        for i in range(min_val, max_val + 1):
            builder.button(
                text=str(i), callback_data=DynamicSurveyAnswerCB(value=str(i))
            )
        builder.adjust(5)
    elif qtype in ("single_choice", "multiple_choice"):
        selected_set = set(selected) if selected else set()
        for opt in question.get("options", []):
            label = (
                f"✓ {opt['label']}" if opt["value"] in selected_set else opt["label"]
            )
            builder.button(
                text=label,
                callback_data=DynamicSurveyAnswerCB(value=opt["value"]),
            )
        if qtype == "multiple_choice":
            builder.button(
                text="Готово", callback_data=DynamicSurveyAnswerCB(value="__done__")
            )
        builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=DynamicSurveyAnswerCB(value="__cancel__").pack(),
        )
    )
    return builder.as_markup()


def _cancel_only_keyboard():
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Отмена",
        callback_data=DynamicSurveyAnswerCB(value="__cancel__"),
    )
    return builder.as_markup()


async def _load_question(question_id: int):
    from src.dao.survey_template import SurveyTemplateDAO

    question = await SurveyTemplateDAO.get_question_by_id(question_id)
    if question is None:
        raise ValueError(f"Question {question_id} not found")
    return question


async def _show_question(
    bot: Bot,
    chat_id: int,
    msg_id: int,
    state: FSMContext,
    idx: int,
    questions: list[dict],
    title: str,
):
    question = questions[idx]
    total = len(questions)
    text = f"<b>{title}</b>\n\nВопрос {idx + 1}/{total}:\n{question['title']}"

    if question["is_required"]:
        text += " *"

    qtype = question["question_type"]

    if qtype == "text":
        await state.set_state(DynamicSurveyFSM.waiting_text)
        if not question["is_required"]:
            text += "\n\n<i>Отправьте текст или «-» чтобы пропустить</i>"
        keyboard = _cancel_only_keyboard()
    else:
        await state.set_state(DynamicSurveyFSM.answering)
        keyboard = _build_keyboard_from_dict(question)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=keyboard,
        )
    except TelegramBadRequest:
        pass


async def _advance(bot: Bot, chat_id: int, msg_id: int, state: FSMContext, data: dict):
    idx = data["current_index"] + 1
    questions = data["questions"]

    if idx >= len(questions):
        service = SurveySessionService()
        await service.complete_session(data["session_id"])
        logger.info("Survey completed: session=%s", data["session_id"])

        respondent_id = data.get("respondent_id")
        if respondent_id:
            invalidate_pending_cache(respondent_id)
            await render_menu_to(bot, chat_id, msg_id, respondent_id, edit=True)

        await state.clear()
        return

    await state.update_data(current_index=idx)

    session_service = SurveySessionService()
    session = await session_service.get_session(data["session_id"])
    title = session.template.title

    await _show_question(bot, chat_id, msg_id, state, idx, questions, title)
