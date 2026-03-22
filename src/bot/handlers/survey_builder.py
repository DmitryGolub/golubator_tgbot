import logging
import re

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from src.bot.callbacks.survey_builder import (
    SurveyBuilderActionCB,
    SurveyQuestionTypeCB,
    SurveyResultsSessionCB,
    SurveyResultsTemplateCB,
    SurveyTemplateDeleteCB,
    SurveyTemplateDetailCB,
    SurveyTemplateToggleCB,
)
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.survey_builder import (
    QUESTION_TYPE_LABELS,
    add_option_keyboard,
    after_question_keyboard,
    cancel_keyboard,
    question_type_keyboard,
    results_sessions_keyboard,
    results_templates_keyboard,
    survey_builder_menu_keyboard,
    template_detail_keyboard,
    templates_list_keyboard,
)
from src.bot.states.survey_builder import SurveyBuilderFSM
from src.dao.survey_session import SurveySessionDAO
from src.dao.user import UserDAO
from src.services.survey_session import SessionNotFoundError, SurveySessionService
from src.services.survey_template import SlugAlreadyExistsError, SurveyTemplateService
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="survey_builder")
router.message.filter(PermissionFilter("manage_surveys"))
router.callback_query.filter(PermissionFilter("manage_surveys"))


# --- Menu ---

@router.callback_query(F.data == "menu_surveys")
async def cb_surveys_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "Конструктор опросов",
        reply_markup=survey_builder_menu_keyboard(),
    )


# --- List templates ---

@router.callback_query(SurveyBuilderActionCB.filter(F.action == "list"))
async def cb_list_templates(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    service = SurveyTemplateService()
    templates = await service.list_active()

    if not templates:
        await callback.answer("Нет созданных опросов")
        return

    await callback.answer()
    await callback.message.edit_text(
        "Список опросов:",
        reply_markup=templates_list_keyboard(templates),
    )


@router.callback_query(SurveyTemplateDetailCB.filter())
async def cb_template_detail(callback: CallbackQuery, callback_data: SurveyTemplateDetailCB):
    service = SurveyTemplateService()
    try:
        template = await service.get(callback_data.template_id)
    except Exception:
        await callback.answer("Опрос не найден")
        return

    questions_text = ""
    for q in template.questions:
        type_label = QUESTION_TYPE_LABELS.get(q.question_type.value, q.question_type.value)
        questions_text += f"\n  {q.sort_order}. {q.title} [{type_label}]"
        if q.options:
            for opt in q.options:
                questions_text += f"\n     - {opt.label} ({opt.value})"

    status = "Активен" if template.is_active else "Отключен"
    text = (
        f"<b>{template.title}</b>\n"
        f"Slug: <code>{template.slug}</code>\n"
        f"Статус: {status}\n"
        f"Вопросов: {len(template.questions)}\n"
        f"{questions_text}"
    )

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=template_detail_keyboard(template))


@router.callback_query(SurveyTemplateToggleCB.filter())
async def cb_toggle_template(callback: CallbackQuery, callback_data: SurveyTemplateToggleCB):
    service = SurveyTemplateService()
    try:
        template = await service.get(callback_data.template_id)
        template = await service.toggle_active(template.id, not template.is_active)
    except Exception:
        await callback.answer("Опрос не найден")
        return

    status = "включен" if template.is_active else "выключен"
    await callback.answer(f"Опрос {status}")
    await callback.message.edit_text(
        f"Опрос <b>{template.title}</b> — {status}.",
        reply_markup=template_detail_keyboard(template),
    )


@router.callback_query(SurveyTemplateDeleteCB.filter())
async def cb_delete_template(callback: CallbackQuery, callback_data: SurveyTemplateDeleteCB):
    service = SurveyTemplateService()
    try:
        await service.delete(callback_data.template_id)
    except Exception:
        await callback.answer("Опрос не найден")
        return

    await callback.answer("Опрос удалён")
    templates = await service.list_active()
    if templates:
        await callback.message.edit_text(
            "Список опросов:",
            reply_markup=templates_list_keyboard(templates),
        )
    else:
        await callback.message.edit_text(
            "Конструктор опросов",
            reply_markup=survey_builder_menu_keyboard(),
        )


# --- Create template FSM ---

@router.callback_query(SurveyBuilderActionCB.filter(F.action == "create"))
async def cb_start_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(SurveyBuilderFSM.entering_title)
    await callback.answer()
    await callback.message.edit_text(
        "Введите название опроса:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyBuilderFSM.entering_title)
async def msg_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Название не может быть пустым. Попробуйте снова:")
        return

    await state.update_data(title=title, questions=[])
    await state.set_state(SurveyBuilderFSM.entering_slug)
    await message.answer(
        "Введите slug (латиница, цифры, подчёркивания).\n"
        "Slug — уникальный идентификатор опроса:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyBuilderFSM.entering_slug)
async def msg_slug(message: Message, state: FSMContext):
    slug = message.text.strip().lower()
    if not re.match(r"^[a-z0-9_]+$", slug):
        await message.answer("Slug может содержать только латиницу, цифры и подчёркивания. Попробуйте снова:")
        return

    await state.update_data(slug=slug)
    await state.set_state(SurveyBuilderFSM.entering_description)
    await message.answer(
        "Введите описание опроса (или отправьте «-» чтобы пропустить):",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyBuilderFSM.entering_description)
async def msg_description(message: Message, state: FSMContext):
    text = message.text.strip()
    description = None if text == "-" else text
    await state.update_data(description=description)

    await state.set_state(SurveyBuilderFSM.adding_question_title)
    await message.answer(
        "Теперь добавим вопросы.\n\nВведите текст первого вопроса:",
        reply_markup=cancel_keyboard(),
    )


# --- Add question ---

@router.message(SurveyBuilderFSM.adding_question_title)
async def msg_question_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Текст вопроса не может быть пустым.")
        return

    await state.update_data(current_question_title=title)
    await state.set_state(SurveyBuilderFSM.choosing_question_type)
    await message.answer("Выберите тип вопроса:", reply_markup=question_type_keyboard())


@router.callback_query(SurveyBuilderFSM.choosing_question_type, SurveyQuestionTypeCB.filter())
async def cb_question_type(callback: CallbackQuery, callback_data: SurveyQuestionTypeCB, state: FSMContext):
    qtype = callback_data.value
    await state.update_data(current_question_type=qtype)
    await callback.answer()

    if qtype == "rating":
        await state.set_state(SurveyBuilderFSM.configuring_rating_min)
        await callback.message.edit_text(
            "Введите минимальное значение рейтинга (обычно 1):",
            reply_markup=cancel_keyboard(),
        )
    elif qtype in ("single_choice", "multiple_choice"):
        await state.update_data(current_options=[])
        await state.set_state(SurveyBuilderFSM.adding_option_value)
        await callback.message.edit_text(
            "Добавьте варианты ответа.\n\n"
            "Введите машинное значение (slug) первого варианта:",
            reply_markup=cancel_keyboard(),
        )
    else:
        await _save_question(callback.message, state)


# --- Rating config ---

@router.message(SurveyBuilderFSM.configuring_rating_min)
async def msg_rating_min(message: Message, state: FSMContext):
    try:
        min_val = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return

    await state.update_data(rating_min=min_val)
    await state.set_state(SurveyBuilderFSM.configuring_rating_max)
    await message.answer(
        "Введите максимальное значение рейтинга (обычно 5 или 10):",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyBuilderFSM.configuring_rating_max)
async def msg_rating_max(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        max_val = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return

    min_val = data.get("rating_min", 1)
    if max_val <= min_val:
        await message.answer(f"Максимум должен быть больше {min_val}. Попробуйте снова:")
        return

    await state.update_data(rating_max=max_val)
    await _save_question(message, state)


# --- Choice options ---

@router.message(SurveyBuilderFSM.adding_option_value)
async def msg_option_value(message: Message, state: FSMContext):
    value = message.text.strip()
    if not re.match(r"^[a-z0-9_]+$", value):
        await message.answer("Значение может содержать только латиницу, цифры и подчёркивания:")
        return

    await state.update_data(current_option_value=value)
    await state.set_state(SurveyBuilderFSM.adding_option_label)
    await message.answer(
        f"Введите отображаемую метку для варианта <code>{value}</code>:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyBuilderFSM.adding_option_label)
async def msg_option_label(message: Message, state: FSMContext):
    label = message.text.strip()
    if not label:
        await message.answer("Метка не может быть пустой:")
        return

    data = await state.get_data()
    options = data.get("current_options", [])
    options.append({"value": data["current_option_value"], "label": label})
    await state.update_data(current_options=options)

    await state.set_state(SurveyBuilderFSM.adding_option_value)

    options_text = "\n".join(f"  - {o['label']} ({o['value']})" for o in options)
    await message.answer(
        f"Добавлено вариантов: {len(options)}\n{options_text}\n\n"
        "Введите значение следующего варианта или нажмите кнопку ниже:",
        reply_markup=add_option_keyboard(),
    )


@router.callback_query(
    SurveyBuilderFSM.adding_option_value,
    SurveyBuilderActionCB.filter(F.action == "options_done"),
)
async def cb_options_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    options = data.get("current_options", [])
    if len(options) < 2:
        await callback.answer("Нужно минимум 2 варианта")
        return

    await callback.answer()
    await _save_question(callback.message, state)


# --- Save question helper ---

async def _save_question(message: Message, state: FSMContext):
    data = await state.get_data()
    questions = data.get("questions", [])

    question = {
        "title": data["current_question_title"],
        "question_type": data["current_question_type"],
        "is_required": True,
        "config": None,
        "options": None,
    }

    qtype = data["current_question_type"]
    if qtype == "rating":
        question["config"] = {"min": data.get("rating_min", 1), "max": data.get("rating_max", 5)}
    elif qtype in ("single_choice", "multiple_choice"):
        question["options"] = data.get("current_options", [])

    questions.append(question)

    await state.update_data(
        questions=questions,
        current_question_title=None,
        current_question_type=None,
        current_options=None,
        current_option_value=None,
        rating_min=None,
        rating_max=None,
    )

    type_label = QUESTION_TYPE_LABELS.get(qtype, qtype)
    await message.answer(
        f"Вопрос #{len(questions)} добавлен: {question['title']} [{type_label}]\n\n"
        "Добавить ещё вопрос или завершить?",
        reply_markup=after_question_keyboard(),
    )


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "add_question"))
async def cb_add_more_question(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SurveyBuilderFSM.adding_question_title)
    await callback.answer()
    await callback.message.edit_text(
        "Введите текст следующего вопроса:",
        reply_markup=cancel_keyboard(),
    )


# --- Finish creating template ---

@router.callback_query(SurveyBuilderActionCB.filter(F.action == "finish"))
async def cb_finish_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data.get("questions", [])

    if not questions:
        await callback.answer("Добавьте хотя бы один вопрос")
        return

    service = SurveyTemplateService()
    try:
        template = await service.create(
            title=data["title"],
            slug=data["slug"],
            description=data.get("description"),
            created_by=callback.from_user.id,
            questions=questions,
        )
    except SlugAlreadyExistsError:
        await callback.answer("Опрос с таким slug уже существует")
        return

    await state.clear()
    await callback.answer("Опрос создан!")

    questions_text = ""
    for q in template.questions:
        type_label = QUESTION_TYPE_LABELS.get(q.question_type.value, q.question_type.value)
        questions_text += f"\n  {q.sort_order}. {q.title} [{type_label}]"

    await callback.message.edit_text(
        f"Опрос <b>{template.title}</b> создан.\n"
        f"Slug: <code>{template.slug}</code>\n"
        f"Вопросов: {len(template.questions)}{questions_text}",
        reply_markup=survey_builder_menu_keyboard(),
    )


# --- Results ---

@router.callback_query(SurveyBuilderActionCB.filter(F.action == "results"))
async def cb_results_templates(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    service = SurveyTemplateService()
    templates = await service.list_active()
    if not templates:
        await callback.answer("Нет опросов")
        return

    await callback.answer()
    await callback.message.edit_text(
        "Выберите опрос для просмотра результатов:",
        reply_markup=results_templates_keyboard(templates),
    )


@router.callback_query(SurveyResultsTemplateCB.filter())
async def cb_results_sessions(callback: CallbackQuery, callback_data: SurveyResultsTemplateCB):
    await callback.answer()
    sessions = await SurveySessionDAO.get_completed_by_template(callback_data.template_id)
    if not sessions:
        await callback.message.edit_text(
            "Завершённых сессий нет.",
            reply_markup=survey_builder_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        f"Завершённых сессий: {len(sessions)}",
        reply_markup=results_sessions_keyboard(sessions),
    )


@router.callback_query(SurveyResultsSessionCB.filter())
async def cb_results_session_detail(callback: CallbackQuery, callback_data: SurveyResultsSessionCB):
    await callback.answer()
    service = SurveySessionService()
    try:
        session = await service.get_session(callback_data.session_id)
    except SessionNotFoundError:
        await callback.message.edit_text(
            "Сессия не найдена.",
            reply_markup=survey_builder_menu_keyboard(),
        )
        return

    respondent_list = await UserDAO.get_all(telegram_id=session.respondent_id)
    respondent = respondent_list[0] if respondent_list else None
    respondent_name = e(respondent.name) if respondent else str(session.respondent_id)

    lines = [
        f"<b>Результаты сессии #{session.id}</b>",
        f"Респондент: {respondent_name}",
        f"Статус: {session.status.value}",
        "",
    ]

    for answer in session.answers:
        q = answer.question
        q_title = e(q.title) if q else f"Вопрос #{answer.question_id}"
        if answer.value_text is not None:
            val = e(answer.value_text)
        elif answer.value_int is not None:
            val = str(answer.value_int)
        elif answer.value_choice is not None:
            val = ", ".join(answer.value_choice)
        else:
            val = "—"
        lines.append(f"<b>{q_title}</b>\n  {val}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=survey_builder_menu_keyboard(),
    )


# --- Cancel ---

@router.callback_query(SurveyBuilderActionCB.filter(F.action == "cancel"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text(
        "Конструктор опросов",
        reply_markup=survey_builder_menu_keyboard(),
    )
