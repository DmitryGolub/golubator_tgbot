import logging
import uuid

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.fsm.context import FSMContext

from src.bot.callbacks.pagination import PageNavCB
from src.bot.callbacks.survey_builder import (
    SurveyAddOptionCB,
    SurveyAddQuestionCB,
    SurveyBuilderActionCB,
    SurveyDeleteOptionCB,
    SurveyEditFieldCB,
    SurveyEditOptionCB,
    SurveyEditQFieldCB,
    SurveyEditQuestionCB,
    SurveyEditQuestionTypeCB,
    SurveyEditTemplateMenuCB,
    SurveyQuestionsListCB,
    SurveyQuestionTypeCB,
    SurveyReorderQCB,
    SurveyResultsSessionCB,
    SurveyResultsTemplateCB,
    SurveySendRecipientCB,
    SurveySendSelectCB,
    SurveyTemplateDeleteCB,
    SurveyTemplateDetailCB,
    SurveyTemplateToggleCB,
)
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.pagination import get_page_slice
from src.bot.keyboards.survey_builder import (
    QUESTION_TYPE_LABELS,
    TEMPLATE_KIND_LABELS,
    add_option_keyboard,
    after_question_keyboard,
    cancel_keyboard,
    edit_options_keyboard,
    edit_question_keyboard,
    edit_template_fields_keyboard,
    question_type_edit_keyboard,
    question_type_keyboard,
    questions_list_keyboard,
    results_sessions_keyboard,
    survey_send_confirm_keyboard,
    survey_send_recipient_type_keyboard,
    template_detail_keyboard,
    template_kind_choice_keyboard,
    templates_list_keyboard,
)
from src.models.survey_template import TemplateKind
from src.bot.pagination_search import filter_items
from src.bot.states.survey_builder import (
    SurveyBuilderFSM,
    SurveyEditFSM,
    SurveySendFSM,
)
from src.bot.utils import safe_edit_text
from src.dao.survey_session import SurveySessionDAO
from src.dao.user import UserDAO
from src.services.survey_session import SessionNotFoundError, SurveySessionService
from src.services.survey_template import (
    OptionNotFoundError,
    QuestionNotFoundError,
    SlugAlreadyExistsError,
    SurveyTemplateService,
    TemplateNotFoundError,
)
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
    text, markup = await _build_surveys_list_page(page=0)
    await safe_edit_text(callback, text, reply_markup=markup)


# --- List templates ---


async def _build_surveys_list_page(
    page: int = 0, search_query: str | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    service = SurveyTemplateService()
    templates = await service.list_active()
    filtered = (
        filter_items(templates, search_query, "surveys_list")
        if search_query
        else templates
    )
    page_items, total_pages = get_page_slice(filtered, page)

    if not filtered:
        return "Нет созданных опросов.", templates_list_keyboard(
            [], page=0, total_pages=1
        )

    lines = ["<b>Список опросов и рассылок:</b>\n"]
    for idx, t in enumerate(page_items):
        global_num = page * 6 + idx + 1
        status = "ON" if t.is_active else "OFF"
        kind_label = TEMPLATE_KIND_LABELS.get(
            t.kind.value if hasattr(t.kind, "value") else t.kind, "Опрос"
        )
        if t.kind == TemplateKind.broadcast:
            preview = (t.body or "—").split("\n", 1)[0][:60]
            extra = f"Текст: {e(preview)}"
        else:
            desc = t.description or "—"
            extra = f"Описание: {e(desc)}"
        lines.append(
            f"{global_num}. [{status}] [{kind_label}] {e(t.title)}\n   {extra}"
        )

    text = "\n\n".join(lines)
    markup = templates_list_keyboard(
        list(page_items),
        page=page,
        total_pages=total_pages,
        search_query=search_query,
    )
    return text, markup


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "list"))
async def cb_list_templates(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("surveys_list")
    text, markup = await _build_surveys_list_page(page=0, search_query=sq)
    await safe_edit_text(callback, text, reply_markup=markup)


@router.callback_query(PageNavCB.filter(F.menu == "surveys_list"))
async def cb_surveys_list_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("surveys_list")
    text, markup = await _build_surveys_list_page(
        page=callback_data.page, search_query=sq
    )
    await safe_edit_text(callback, text, reply_markup=markup)
    await callback.answer()


def _format_template_detail(template) -> str:
    status = "Активен" if template.is_active else "Отключен"
    kind_label = TEMPLATE_KIND_LABELS.get(
        template.kind.value if hasattr(template.kind, "value") else template.kind,
        "Опрос",
    )

    if template.kind == TemplateKind.broadcast:
        body = template.body or "—"
        return (
            f"<b>{e(template.title)}</b>\n"
            f"Тип: {kind_label}\n"
            f"Slug: <code>{e(template.slug)}</code>\n"
            f"Статус: {status}\n\n"
            f"<b>Текст рассылки:</b>\n{e(body)}"
        )

    questions_text = ""
    for q in template.questions:
        type_label = QUESTION_TYPE_LABELS.get(
            q.question_type.value, q.question_type.value
        )
        questions_text += f"\n  {q.sort_order}. {e(q.title)} [{type_label}]"
        if q.options:
            for opt in q.options:
                questions_text += f"\n     - {e(opt.label)} ({e(opt.value)})"

    description = template.description or "—"
    return (
        f"<b>{e(template.title)}</b>\n"
        f"Тип: {kind_label}\n"
        f"Slug: <code>{e(template.slug)}</code>\n"
        f"Описание: {e(description)}\n"
        f"Статус: {status}\n"
        f"Вопросов: {len(template.questions)}\n"
        f"{questions_text}"
    )


def _format_question_detail(question) -> str:
    qtype = (
        question.question_type.value
        if hasattr(question.question_type, "value")
        else question.question_type
    )
    type_label = QUESTION_TYPE_LABELS.get(qtype, qtype)
    lines = [
        f"<b>Вопрос #{question.sort_order}</b>",
        f"Текст: {e(question.title)}",
        f"Тип: {type_label}",
    ]
    if qtype == "rating" and question.config:
        cfg = question.config
        lines.append(f"Рейтинг: {cfg.get('min', 1)}–{cfg.get('max', 10)}")
    if question.options:
        lines.append("Варианты:")
        for opt in question.options:
            lines.append(f"  - {e(opt.label)} ({e(opt.value)})")
    return "\n".join(lines)


async def _show_template_detail_cb(callback: CallbackQuery, template_id: int) -> None:
    service = SurveyTemplateService()
    try:
        template = await service.get(template_id)
    except TemplateNotFoundError:
        await safe_edit_text(callback, "Опрос не найден")
        return
    text = _format_template_detail(template)
    await safe_edit_text(
        callback, text, reply_markup=template_detail_keyboard(template)
    )


async def _show_template_detail_msg(message: Message, template_id: int) -> None:
    service = SurveyTemplateService()
    try:
        template = await service.get(template_id)
    except TemplateNotFoundError:
        await message.answer("Опрос не найден")
        return
    text = _format_template_detail(template)
    await message.answer(text, reply_markup=template_detail_keyboard(template))


async def _show_question_detail_cb(callback: CallbackQuery, question_id: int) -> None:
    service = SurveyTemplateService()
    try:
        question = await service.get_question(question_id)
    except QuestionNotFoundError:
        await safe_edit_text(callback, "Вопрос не найден")
        return
    text = _format_question_detail(question)
    await safe_edit_text(callback, text, reply_markup=edit_question_keyboard(question))


async def _show_question_detail_msg(message: Message, question_id: int) -> None:
    service = SurveyTemplateService()
    try:
        question = await service.get_question(question_id)
    except QuestionNotFoundError:
        await message.answer("Вопрос не найден")
        return
    text = _format_question_detail(question)
    await message.answer(text, reply_markup=edit_question_keyboard(question))


async def _show_questions_list_cb(callback: CallbackQuery, template_id: int) -> None:
    service = SurveyTemplateService()
    try:
        template = await service.get(template_id)
    except TemplateNotFoundError:
        await safe_edit_text(callback, "Опрос не найден")
        return
    text = f"<b>Вопросы опроса «{e(template.title)}»</b>\n\n"
    if not template.questions:
        text += "Вопросов пока нет."
    else:
        for q in template.questions:
            type_label = QUESTION_TYPE_LABELS.get(
                q.question_type.value, q.question_type.value
            )
            text += f"{q.sort_order}. {e(q.title)} [{type_label}]\n"
    await safe_edit_text(callback, text, reply_markup=questions_list_keyboard(template))


async def _show_questions_list_msg(message: Message, template_id: int) -> None:
    service = SurveyTemplateService()
    try:
        template = await service.get(template_id)
    except TemplateNotFoundError:
        await message.answer("Опрос не найден")
        return
    text = f"<b>Вопросы опроса «{e(template.title)}»</b>\n\n"
    if not template.questions:
        text += "Вопросов пока нет."
    else:
        for q in template.questions:
            type_label = QUESTION_TYPE_LABELS.get(
                q.question_type.value, q.question_type.value
            )
            text += f"{q.sort_order}. {e(q.title)} [{type_label}]\n"
    await message.answer(text, reply_markup=questions_list_keyboard(template))


async def _show_options_edit_cb(callback: CallbackQuery, question_id: int) -> None:
    service = SurveyTemplateService()
    try:
        question = await service.get_question(question_id)
    except QuestionNotFoundError:
        await safe_edit_text(callback, "Вопрос не найден")
        return
    text = f"<b>Варианты ответа для вопроса «{e(question.title)}»</b>\n\n"
    if not question.options:
        text += "Нет вариантов."
    else:
        for opt in question.options:
            text += f"{opt.sort_order}. {e(opt.label)} ({e(opt.value)})\n"
    await safe_edit_text(callback, text, reply_markup=edit_options_keyboard(question))


async def _show_options_edit_msg(message: Message, question_id: int) -> None:
    service = SurveyTemplateService()
    try:
        question = await service.get_question(question_id)
    except QuestionNotFoundError:
        await message.answer("Вопрос не найден")
        return
    text = f"<b>Варианты ответа для вопроса «{e(question.title)}»</b>\n\n"
    if not question.options:
        text += "Нет вариантов."
    else:
        for opt in question.options:
            text += f"{opt.sort_order}. {e(opt.label)} ({e(opt.value)})\n"
    await message.answer(text, reply_markup=edit_options_keyboard(question))


@router.callback_query(SurveyTemplateDetailCB.filter())
async def cb_template_detail(
    callback: CallbackQuery,
    callback_data: SurveyTemplateDetailCB,
    state: FSMContext,
):
    await callback.answer()
    await state.clear()
    await _show_template_detail_cb(callback, callback_data.template_id)


@router.callback_query(SurveyTemplateToggleCB.filter())
async def cb_toggle_template(
    callback: CallbackQuery, callback_data: SurveyTemplateToggleCB
):
    await callback.answer()
    service = SurveyTemplateService()
    try:
        template = await service.get(callback_data.template_id)
        template = await service.toggle_active(template.id, not template.is_active)
    except TemplateNotFoundError:
        await safe_edit_text(callback, "Опрос не найден")
        return
    except Exception:
        logger.exception("Unexpected error in cb_toggle_template")
        await safe_edit_text(callback, "Произошла ошибка")
        return

    status = "включен" if template.is_active else "выключен"
    await safe_edit_text(
        callback,
        f"Опрос <b>{template.title}</b> — {status}.",
        reply_markup=template_detail_keyboard(template),
    )


@router.callback_query(SurveyTemplateDeleteCB.filter())
async def cb_delete_template(
    callback: CallbackQuery, callback_data: SurveyTemplateDeleteCB
):
    await callback.answer()
    service = SurveyTemplateService()
    try:
        await service.delete(callback_data.template_id)
    except TemplateNotFoundError:
        await safe_edit_text(callback, "Опрос не найден")
        return
    except Exception:
        logger.exception("Unexpected error in cb_delete_template")
        await safe_edit_text(callback, "Произошла ошибка")
        return

    text, markup = await _build_surveys_list_page(page=0)
    await safe_edit_text(callback, text, reply_markup=markup)


# --- Create template FSM ---


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "create"))
async def cb_start_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(SurveyBuilderFSM.choosing_kind)
    await callback.answer()
    await safe_edit_text(
        callback,
        "Что создаём?",
        reply_markup=template_kind_choice_keyboard(),
    )


@router.callback_query(
    SurveyBuilderFSM.choosing_kind,
    SurveyBuilderActionCB.filter(F.action.in_({"kind_survey", "kind_broadcast"})),
)
async def cb_choose_kind(
    callback: CallbackQuery,
    callback_data: SurveyBuilderActionCB,
    state: FSMContext,
):
    kind = (
        TemplateKind.broadcast
        if callback_data.action == "kind_broadcast"
        else TemplateKind.survey
    )
    await state.update_data(kind=kind.value)
    await state.set_state(SurveyBuilderFSM.entering_title)
    await callback.answer()
    prompt = (
        "Введите название рассылки:"
        if kind == TemplateKind.broadcast
        else "Введите название опроса:"
    )
    await safe_edit_text(callback, prompt, reply_markup=cancel_keyboard())


@router.message(SurveyBuilderFSM.entering_title)
async def msg_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Название не может быть пустым. Попробуйте снова:")
        return

    slug = uuid.uuid4().hex[:12]
    data = await state.get_data()
    kind = data.get("kind", TemplateKind.survey.value)
    await state.update_data(title=title, slug=slug, questions=[])

    if kind == TemplateKind.broadcast.value:
        await state.set_state(SurveyBuilderFSM.entering_body)
        await message.answer(
            "Введите текст рассылки. Поддерживаются HTML-теги "
            "и плейсхолдеры $general_chat_link, $mentor_channel_link.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.set_state(SurveyBuilderFSM.entering_description)
    await message.answer(
        "Введите описание опроса (или отправьте «-» чтобы пропустить):",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyBuilderFSM.entering_body)
async def msg_broadcast_body(message: Message, state: FSMContext):
    body = (message.text or "").strip()
    if not body:
        await message.answer("Текст рассылки не может быть пустым.")
        return

    data = await state.get_data()
    service = SurveyTemplateService()
    try:
        template = await service.create(
            title=data["title"],
            slug=data["slug"],
            kind=TemplateKind.broadcast,
            body=body,
            created_by=message.from_user.id,
        )
    except SlugAlreadyExistsError:
        await message.answer("Не удалось создать рассылку. Попробуйте ещё раз.")
        return

    await state.clear()
    text, markup = await _build_surveys_list_page(page=0)
    await message.answer(
        f"Рассылка <b>{e(template.title)}</b> создана.\n\n{text}",
        reply_markup=markup,
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


@router.callback_query(
    SurveyBuilderFSM.choosing_question_type, SurveyQuestionTypeCB.filter()
)
async def cb_question_type(
    callback: CallbackQuery, callback_data: SurveyQuestionTypeCB, state: FSMContext
):
    qtype = callback_data.value
    await state.update_data(current_question_type=qtype)
    await callback.answer()

    if qtype == "rating":
        await state.set_state(SurveyBuilderFSM.configuring_rating_min)
        await safe_edit_text(
            callback,
            "Введите минимальное значение рейтинга (обычно 1):",
            reply_markup=cancel_keyboard(),
        )
    elif qtype in ("single_choice", "multiple_choice"):
        await state.update_data(current_options=[])
        await state.set_state(SurveyBuilderFSM.adding_option_label)
        await safe_edit_text(
            callback,
            "Добавьте варианты ответа.\n\nВведите метку первого варианта:",
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
        "Введите максимальное значение рейтинга (по умолчанию 10):",
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
        await message.answer(
            f"Максимум должен быть больше {min_val}. Попробуйте снова:"
        )
        return

    await state.update_data(rating_max=max_val)
    await _save_question(message, state)


# --- Choice options ---


@router.message(SurveyBuilderFSM.adding_option_label)
async def msg_option_label(message: Message, state: FSMContext):
    label = message.text.strip()
    if not label:
        await message.answer("Метка не может быть пустой:")
        return

    data = await state.get_data()
    options = data.get("current_options", [])
    value = f"opt_{len(options) + 1}"
    options.append({"value": value, "label": label})
    await state.update_data(current_options=options)

    options_text = "\n".join(f"  - {o['label']} ({o['value']})" for o in options)
    await message.answer(
        f"Добавлено вариантов: {len(options)}\n{options_text}\n\n"
        "Введите метку следующего варианта или нажмите кнопку ниже:",
        reply_markup=add_option_keyboard(),
    )


@router.callback_query(
    SurveyBuilderFSM.adding_option_label,
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
        question["config"] = {
            "min": data.get("rating_min", 1),
            "max": data.get("rating_max", 10),
        }
    elif qtype in ("single_choice", "multiple_choice"):
        question["options"] = data.get("current_options", [])

    questions.append(question)

    await state.update_data(
        questions=questions,
        current_question_title=None,
        current_question_type=None,
        current_options=None,
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
    data = await state.get_data()
    if "questions" not in data:
        await callback.answer("Сессия устарела. Начните создание заново.")
        return
    await state.set_state(SurveyBuilderFSM.adding_question_title)
    await callback.answer()
    await safe_edit_text(
        callback,
        "Введите текст следующего вопроса:",
        reply_markup=cancel_keyboard(),
    )


# --- Finish creating template ---


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "finish"))
async def cb_finish_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("title") or not data.get("slug"):
        await callback.answer("Сессия устарела. Начните создание заново.")
        return

    questions = data.get("questions", [])

    if not questions:
        await callback.answer("Добавьте хотя бы один вопрос")
        return

    await callback.answer()
    service = SurveyTemplateService()
    try:
        template = await service.create(
            title=data["title"],
            slug=data["slug"],
            kind=TemplateKind.survey,
            description=data.get("description"),
            created_by=callback.from_user.id,
            questions=questions,
        )
    except SlugAlreadyExistsError:
        await safe_edit_text(callback, "Не удалось создать опрос. Попробуйте ещё раз.")
        return

    await state.clear()

    questions_text = ""
    for q in template.questions:
        type_label = QUESTION_TYPE_LABELS.get(
            q.question_type.value, q.question_type.value
        )
        questions_text += f"\n  {q.sort_order}. {q.title} [{type_label}]"

    text, markup = await _build_surveys_list_page(page=0)
    await safe_edit_text(
        callback,
        f"Опрос <b>{template.title}</b> создан.\n"
        f"Slug: <code>{template.slug}</code>\n"
        f"Вопросов: {len(template.questions)}{questions_text}\n\n{text}",
        reply_markup=markup,
    )


# --- Results ---


@router.callback_query(SurveyResultsTemplateCB.filter())
async def cb_results_sessions(
    callback: CallbackQuery, callback_data: SurveyResultsTemplateCB
):
    await callback.answer()
    sessions = await SurveySessionDAO.get_completed_by_template(
        callback_data.template_id
    )
    if not sessions:
        back_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data=SurveyBuilderActionCB(action="list").pack(),
                    )
                ]
            ]
        )
        await safe_edit_text(
            callback,
            "Завершённых сессий нет.",
            reply_markup=back_kb,
        )
        return

    await safe_edit_text(
        callback,
        f"Завершённых сессий: {len(sessions)}",
        reply_markup=results_sessions_keyboard(sessions),
    )


@router.callback_query(SurveyResultsSessionCB.filter())
async def cb_results_session_detail(
    callback: CallbackQuery, callback_data: SurveyResultsSessionCB
):
    await callback.answer()
    service = SurveySessionService()
    try:
        session = await service.get_session(callback_data.session_id)
    except SessionNotFoundError:
        back_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data=SurveyBuilderActionCB(action="list").pack(),
                    )
                ]
            ]
        )
        await safe_edit_text(
            callback,
            "Сессия не найдена.",
            reply_markup=back_kb,
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
            if q and q.options:
                label_map = {opt.value: opt.label for opt in q.options}
                val = ", ".join(label_map.get(v, v) for v in answer.value_choice)
            else:
                val = ", ".join(answer.value_choice)
        else:
            val = "—"
        lines.append(f"<b>{q_title}</b>\n  {val}")

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=SurveyResultsTemplateCB(
                        template_id=session.template_id
                    ).pack(),
                )
            ]
        ]
    )
    await safe_edit_text(
        callback,
        "\n".join(lines),
        reply_markup=back_kb,
    )


# --- Manual send ---

RECIPIENT_TYPE_LABELS = {
    "by_role": "По роли",
    "by_state": "По статусу",
    "by_cohort": "По когорте",
    "specific_users": "Конкретные пользователи",
}

RECIPIENT_HINTS = {
    "by_role": "Введите название роли (например: mentor):",
    "by_state": "Введите статус (greeting/hold/study/search/offer):",
    "by_cohort": "Введите значение когорты:",
    "specific_users": "Введите Telegram ID пользователей через запятую:",
}


@router.callback_query(SurveySendSelectCB.filter())
async def cb_send_select_template(
    callback: CallbackQuery, callback_data: SurveySendSelectCB, state: FSMContext
):
    await callback.answer()
    service = SurveyTemplateService()
    try:
        template = await service.get(callback_data.template_id)
    except TemplateNotFoundError:
        await safe_edit_text(callback, "Опрос не найден.")
        return

    await state.update_data(
        send_template_id=template.id,
        send_template_title=template.title,
    )
    await state.set_state(SurveySendFSM.choosing_recipient_type)
    await safe_edit_text(
        callback,
        f"Опрос: <b>{e(template.title)}</b>\n\nВыберите тип получателей:",
        reply_markup=survey_send_recipient_type_keyboard(),
    )


@router.callback_query(
    SurveySendFSM.choosing_recipient_type, SurveySendRecipientCB.filter()
)
async def cb_send_recipient_type(
    callback: CallbackQuery, callback_data: SurveySendRecipientCB, state: FSMContext
):
    rt = callback_data.value
    await state.update_data(send_recipient_type=rt)
    await callback.answer()
    await state.set_state(SurveySendFSM.configuring_recipients)
    await safe_edit_text(callback, RECIPIENT_HINTS[rt], reply_markup=cancel_keyboard())


@router.message(SurveySendFSM.configuring_recipients)
async def msg_send_recipient_config(message: Message, state: FSMContext):
    data = await state.get_data()
    rt = data["send_recipient_type"]
    text = message.text.strip()

    config = {}
    if rt == "by_role":
        config = {"role_name": text}
    elif rt == "by_state":
        config = {"state": text}
    elif rt == "by_cohort":
        config = {"cohort_value": text}
    elif rt == "specific_users":
        user_ids = [
            int(uid.strip()) for uid in text.split(",") if uid.strip().isdigit()
        ]
        if not user_ids:
            await message.answer(
                "Введите хотя бы один числовой Telegram ID через запятую."
            )
            return
        config = {"user_ids": user_ids}

    await state.update_data(send_recipient_config=config)
    await state.set_state(SurveySendFSM.confirming)

    template_title = e(data["send_template_title"])
    rt_label = RECIPIENT_TYPE_LABELS.get(rt, rt)
    config_str = text

    await message.answer(
        f"<b>Подтверждение отправки</b>\n\n"
        f"Опрос: <b>{template_title}</b>\n"
        f"Получатели: {rt_label}\n"
        f"Конфигурация: <code>{e(config_str)}</code>",
        reply_markup=survey_send_confirm_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(
    SurveySendFSM.confirming, SurveyBuilderActionCB.filter(F.action == "send_confirm")
)
async def cb_send_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()

    template_id = data["send_template_id"]
    template_title = data["send_template_title"]
    recipient_type = data["send_recipient_type"]
    recipient_config = data["send_recipient_config"]

    await safe_edit_text(callback, "Отправка опроса...")

    from src.services.survey_direct_send import SurveyDirectSendService

    sent = await SurveyDirectSendService.send_survey(
        template_id=template_id,
        template_title=template_title,
        recipient_type=recipient_type,
        recipient_config=recipient_config,
        bot=callback.bot,
    )

    await state.clear()
    text, markup = await _build_surveys_list_page(page=0)
    await safe_edit_text(
        callback,
        f"Опрос <b>{e(template_title)}</b> отправлен.\nПолучателей: <b>{sent}</b>\n\n{text}",
        reply_markup=markup,
    )


# --- Cancel ---


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "cancel"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    edit_template_id = data.get("edit_template_id")
    edit_question_id = data.get("edit_question_id")
    await state.clear()
    await callback.answer("Отменено")
    if edit_question_id:
        await _show_question_detail_cb(callback, edit_question_id)
    elif edit_template_id:
        await _show_template_detail_cb(callback, edit_template_id)
    else:
        text, markup = await _build_surveys_list_page(page=0)
        await safe_edit_text(callback, text, reply_markup=markup)


# --- Edit template fields ---


@router.callback_query(SurveyEditTemplateMenuCB.filter())
async def cb_edit_template_menu(
    callback: CallbackQuery,
    callback_data: SurveyEditTemplateMenuCB,
    state: FSMContext,
):
    await callback.answer()
    await state.clear()
    await state.update_data(edit_template_id=callback_data.template_id)
    service = SurveyTemplateService()
    try:
        template = await service.get(callback_data.template_id)
    except TemplateNotFoundError:
        await safe_edit_text(callback, "Опрос не найден.")
        return
    await safe_edit_text(
        callback,
        "Что редактируем?",
        reply_markup=edit_template_fields_keyboard(
            callback_data.template_id,
            is_broadcast=template.kind == TemplateKind.broadcast,
        ),
    )


@router.callback_query(SurveyEditFieldCB.filter())
async def cb_edit_field_chosen(
    callback: CallbackQuery,
    callback_data: SurveyEditFieldCB,
    state: FSMContext,
):
    await callback.answer()
    await state.update_data(edit_template_id=callback_data.template_id)
    field = callback_data.field
    prompts = {
        "title": "Введите новое название:",
        "description": "Введите новое описание опроса (или «-» чтобы очистить):",
        "slug": "Введите новый slug:",
        "body": "Введите новый текст рассылки:",
    }
    states = {
        "title": SurveyEditFSM.editing_title,
        "description": SurveyEditFSM.editing_description,
        "slug": SurveyEditFSM.editing_slug,
        "body": SurveyEditFSM.editing_body,
    }
    if field not in prompts:
        return
    await state.set_state(states[field])
    await safe_edit_text(callback, prompts[field], reply_markup=cancel_keyboard())


@router.message(SurveyEditFSM.editing_body)
async def msg_edit_template_body(message: Message, state: FSMContext):
    body = (message.text or "").strip()
    if not body:
        await message.answer("Текст не может быть пустым.")
        return
    data = await state.get_data()
    template_id = data["edit_template_id"]
    service = SurveyTemplateService()
    try:
        await service.update_template(template_id, body=body)
    except TemplateNotFoundError:
        await message.answer("Шаблон не найден.")
        await state.clear()
        return
    await state.clear()
    await _show_template_detail_msg(message, template_id)


@router.message(SurveyEditFSM.editing_title)
async def msg_edit_template_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    data = await state.get_data()
    template_id = data["edit_template_id"]
    service = SurveyTemplateService()
    try:
        await service.update_template(template_id, title=title)
    except TemplateNotFoundError:
        await message.answer("Опрос не найден.")
        await state.clear()
        return
    await state.clear()
    await _show_template_detail_msg(message, template_id)


@router.message(SurveyEditFSM.editing_description)
async def msg_edit_template_description(message: Message, state: FSMContext):
    text = message.text.strip()
    description = None if text == "-" else text
    data = await state.get_data()
    template_id = data["edit_template_id"]
    service = SurveyTemplateService()
    try:
        await service.update_template(template_id, description=description)
    except TemplateNotFoundError:
        await message.answer("Опрос не найден.")
        await state.clear()
        return
    await state.clear()
    await _show_template_detail_msg(message, template_id)


@router.message(SurveyEditFSM.editing_slug)
async def msg_edit_template_slug(message: Message, state: FSMContext):
    slug = message.text.strip()
    if not slug:
        await message.answer("Slug не может быть пустым.")
        return
    data = await state.get_data()
    template_id = data["edit_template_id"]
    service = SurveyTemplateService()
    try:
        await service.update_template(template_id, slug=slug)
    except SlugAlreadyExistsError:
        await message.answer("Такой slug уже используется. Попробуйте другой:")
        return
    except TemplateNotFoundError:
        await message.answer("Опрос не найден.")
        await state.clear()
        return
    await state.clear()
    await _show_template_detail_msg(message, template_id)


# --- Questions list ---


@router.callback_query(SurveyQuestionsListCB.filter())
async def cb_questions_list(
    callback: CallbackQuery,
    callback_data: SurveyQuestionsListCB,
    state: FSMContext,
):
    await callback.answer()
    await state.clear()
    await state.update_data(edit_template_id=callback_data.template_id)
    await _show_questions_list_cb(callback, callback_data.template_id)


# --- Edit question ---


@router.callback_query(SurveyEditQuestionCB.filter())
async def cb_edit_question(
    callback: CallbackQuery,
    callback_data: SurveyEditQuestionCB,
    state: FSMContext,
):
    await callback.answer()
    service = SurveyTemplateService()
    try:
        question = await service.get_question(callback_data.question_id)
    except QuestionNotFoundError:
        await safe_edit_text(callback, "Вопрос не найден.")
        return
    await state.clear()
    await state.update_data(
        edit_question_id=question.id,
        edit_template_id=question.template_id,
    )
    await safe_edit_text(
        callback,
        _format_question_detail(question),
        reply_markup=edit_question_keyboard(question),
    )


@router.callback_query(SurveyEditQFieldCB.filter())
async def cb_edit_question_field(
    callback: CallbackQuery,
    callback_data: SurveyEditQFieldCB,
    state: FSMContext,
):
    await callback.answer()
    question_id = callback_data.question_id
    field = callback_data.field
    service = SurveyTemplateService()
    try:
        question = await service.get_question(question_id)
    except QuestionNotFoundError:
        await safe_edit_text(callback, "Вопрос не найден.")
        return

    await state.update_data(
        edit_question_id=question_id,
        edit_template_id=question.template_id,
    )

    if field == "title":
        await state.set_state(SurveyEditFSM.editing_question_title)
        await safe_edit_text(
            callback,
            "Введите новый текст вопроса:",
            reply_markup=cancel_keyboard(),
        )
    elif field == "type":
        await safe_edit_text(
            callback,
            "Выберите новый тип вопроса:",
            reply_markup=question_type_edit_keyboard(question_id),
        )
    elif field == "config":
        await state.set_state(SurveyEditFSM.editing_rating_min)
        await safe_edit_text(
            callback,
            "Введите минимальное значение рейтинга:",
            reply_markup=cancel_keyboard(),
        )
    elif field == "options":
        await _show_options_edit_cb(callback, question_id)
    elif field == "delete":
        template_id = question.template_id
        try:
            await service.delete_question(question_id)
        except QuestionNotFoundError:
            await safe_edit_text(callback, "Вопрос не найден.")
            return
        await state.clear()
        await state.update_data(edit_template_id=template_id)
        await _show_questions_list_cb(callback, template_id)


@router.message(SurveyEditFSM.editing_question_title)
async def msg_edit_question_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Текст вопроса не может быть пустым.")
        return
    data = await state.get_data()
    question_id = data["edit_question_id"]
    service = SurveyTemplateService()
    try:
        await service.update_question(question_id, title=title)
    except QuestionNotFoundError:
        await message.answer("Вопрос не найден.")
        await state.clear()
        return
    await state.clear()
    await state.update_data(edit_question_id=question_id)
    await _show_question_detail_msg(message, question_id)


@router.callback_query(SurveyEditQuestionTypeCB.filter())
async def cb_edit_question_type(
    callback: CallbackQuery,
    callback_data: SurveyEditQuestionTypeCB,
    state: FSMContext,
):
    await callback.answer()
    question_id = callback_data.question_id
    new_type = callback_data.value
    service = SurveyTemplateService()
    try:
        question = await service.get_question(question_id)
    except QuestionNotFoundError:
        await safe_edit_text(callback, "Вопрос не найден.")
        return

    await state.update_data(
        edit_question_id=question_id,
        edit_template_id=question.template_id,
    )

    if new_type == "text":
        await service.update_question(question_id, question_type=new_type, config=None)
        await service.replace_question_options(question_id, [])
        await _show_question_detail_cb(callback, question_id)
    elif new_type == "rating":
        await service.replace_question_options(question_id, [])
        await state.update_data(pending_question_type=new_type)
        await state.set_state(SurveyEditFSM.editing_rating_min)
        await safe_edit_text(
            callback,
            "Введите минимальное значение рейтинга:",
            reply_markup=cancel_keyboard(),
        )
    elif new_type in ("single_choice", "multiple_choice"):
        await state.update_data(
            pending_question_type=new_type,
            pending_options=[],
        )
        await service.update_question(question_id, config=None)
        await state.set_state(SurveyEditFSM.adding_question_option)
        await safe_edit_text(
            callback,
            "Добавьте варианты ответа.\n\nВведите метку первого варианта:",
            reply_markup=cancel_keyboard(),
        )


@router.message(SurveyEditFSM.editing_rating_min)
async def msg_edit_rating_min(message: Message, state: FSMContext):
    try:
        min_val = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    await state.update_data(rating_min=min_val)
    await state.set_state(SurveyEditFSM.editing_rating_max)
    await message.answer(
        "Введите максимальное значение рейтинга:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyEditFSM.editing_rating_max)
async def msg_edit_rating_max(message: Message, state: FSMContext):
    try:
        max_val = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    data = await state.get_data()
    min_val = data.get("rating_min", 1)
    if max_val <= min_val:
        await message.answer(
            f"Максимум должен быть больше {min_val}. Попробуйте снова:"
        )
        return
    question_id = data["edit_question_id"]
    service = SurveyTemplateService()
    update_kwargs = {"config": {"min": min_val, "max": max_val}}
    pending_type = data.get("pending_question_type")
    if pending_type:
        update_kwargs["question_type"] = pending_type
    try:
        await service.update_question(question_id, **update_kwargs)
    except QuestionNotFoundError:
        await message.answer("Вопрос не найден.")
        await state.clear()
        return
    await state.clear()
    await state.update_data(edit_question_id=question_id)
    await _show_question_detail_msg(message, question_id)


# --- Options editing ---


@router.callback_query(SurveyEditOptionCB.filter())
async def cb_edit_option(
    callback: CallbackQuery,
    callback_data: SurveyEditOptionCB,
    state: FSMContext,
):
    await callback.answer()
    await state.update_data(edit_option_id=callback_data.option_id)
    await state.set_state(SurveyEditFSM.editing_option_label)
    await safe_edit_text(
        callback,
        "Введите новую метку варианта:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyEditFSM.editing_option_label)
async def msg_edit_option_label(message: Message, state: FSMContext):
    label = message.text.strip()
    if not label:
        await message.answer("Метка не может быть пустой.")
        return
    data = await state.get_data()
    option_id = data["edit_option_id"]
    question_id = data["edit_question_id"]
    service = SurveyTemplateService()
    try:
        await service.update_option(option_id, label=label)
    except OptionNotFoundError:
        await message.answer("Вариант не найден.")
        await state.clear()
        return
    await state.set_state(None)
    await _show_options_edit_msg(message, question_id)


@router.callback_query(SurveyDeleteOptionCB.filter())
async def cb_delete_option(
    callback: CallbackQuery,
    callback_data: SurveyDeleteOptionCB,
    state: FSMContext,
):
    data = await state.get_data()
    question_id = data.get("edit_question_id")
    if not question_id:
        await callback.answer("Сессия устарела.")
        return
    service = SurveyTemplateService()
    try:
        question = await service.get_question(question_id)
    except QuestionNotFoundError:
        await callback.answer("Вопрос не найден.")
        return
    if len(question.options) <= 2:
        await callback.answer("Должно остаться минимум 2 варианта.", show_alert=True)
        return
    try:
        await service.delete_option(callback_data.option_id)
    except OptionNotFoundError:
        await callback.answer("Вариант не найден.")
        return
    await callback.answer("Удалено")
    await _show_options_edit_cb(callback, question_id)


@router.callback_query(SurveyAddOptionCB.filter())
async def cb_add_option(
    callback: CallbackQuery,
    callback_data: SurveyAddOptionCB,
    state: FSMContext,
):
    await callback.answer()
    await state.update_data(edit_question_id=callback_data.question_id)
    await state.set_state(SurveyEditFSM.adding_option_label)
    await safe_edit_text(
        callback,
        "Введите метку нового варианта:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyEditFSM.adding_option_label)
async def msg_add_option_label(message: Message, state: FSMContext):
    label = message.text.strip()
    if not label:
        await message.answer("Метка не может быть пустой.")
        return
    data = await state.get_data()
    question_id = data["edit_question_id"]
    service = SurveyTemplateService()
    try:
        question = await service.get_question(question_id)
    except QuestionNotFoundError:
        await message.answer("Вопрос не найден.")
        await state.clear()
        return
    next_index = len(question.options) + 1
    value = f"opt_{next_index}"
    await service.add_option(question_id=question_id, value=value, label=label)
    await state.set_state(None)
    await _show_options_edit_msg(message, question_id)


# --- Reorder question ---


@router.callback_query(SurveyReorderQCB.filter())
async def cb_reorder_question(
    callback: CallbackQuery,
    callback_data: SurveyReorderQCB,
    state: FSMContext,
):
    service = SurveyTemplateService()
    result = await service.swap_question_order(
        callback_data.question_id, callback_data.direction
    )
    if not result:
        await callback.answer("Невозможно переместить.", show_alert=False)
        return
    await callback.answer("Порядок обновлён")
    await _show_question_detail_cb(callback, callback_data.question_id)


# --- Add question to existing template ---


@router.callback_query(SurveyAddQuestionCB.filter())
async def cb_add_question_to_template(
    callback: CallbackQuery,
    callback_data: SurveyAddQuestionCB,
    state: FSMContext,
):
    await callback.answer()
    await state.clear()
    await state.update_data(edit_template_id=callback_data.template_id)
    await state.set_state(SurveyEditFSM.adding_question_title)
    await safe_edit_text(
        callback,
        "Введите текст нового вопроса:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyEditFSM.adding_question_title)
async def msg_add_question_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Текст вопроса не может быть пустым.")
        return
    await state.update_data(new_question_title=title)
    await state.set_state(SurveyEditFSM.adding_question_type)
    await message.answer("Выберите тип вопроса:", reply_markup=question_type_keyboard())


@router.callback_query(
    SurveyEditFSM.adding_question_type, SurveyQuestionTypeCB.filter()
)
async def cb_add_question_type(
    callback: CallbackQuery,
    callback_data: SurveyQuestionTypeCB,
    state: FSMContext,
):
    qtype = callback_data.value
    await state.update_data(new_question_type=qtype, new_question_options=[])
    await callback.answer()

    if qtype == "rating":
        await state.set_state(SurveyEditFSM.adding_question_rating_min)
        await safe_edit_text(
            callback,
            "Введите минимальное значение рейтинга:",
            reply_markup=cancel_keyboard(),
        )
    elif qtype in ("single_choice", "multiple_choice"):
        await state.set_state(SurveyEditFSM.adding_question_option)
        await safe_edit_text(
            callback,
            "Добавьте варианты ответа.\n\nВведите метку первого варианта:",
            reply_markup=cancel_keyboard(),
        )
    else:
        await _save_new_question(callback.message, state)


@router.message(SurveyEditFSM.adding_question_rating_min)
async def msg_add_q_rating_min(message: Message, state: FSMContext):
    try:
        min_val = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    await state.update_data(new_rating_min=min_val)
    await state.set_state(SurveyEditFSM.adding_question_rating_max)
    await message.answer(
        "Введите максимальное значение рейтинга:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyEditFSM.adding_question_rating_max)
async def msg_add_q_rating_max(message: Message, state: FSMContext):
    try:
        max_val = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    data = await state.get_data()
    min_val = data.get("new_rating_min", 1)
    if max_val <= min_val:
        await message.answer(
            f"Максимум должен быть больше {min_val}. Попробуйте снова:"
        )
        return
    await state.update_data(new_rating_max=max_val)
    await _save_new_question(message, state)


@router.message(SurveyEditFSM.adding_question_option)
async def msg_add_q_option(message: Message, state: FSMContext):
    label = message.text.strip()
    if not label:
        await message.answer("Метка не может быть пустой:")
        return
    data = await state.get_data()

    # Two flows: adding a brand-new question (has new_question_title)
    # OR switching existing question type to choice (has edit_question_id).
    if data.get("new_question_title"):
        options = data.get("new_question_options", [])
        value = f"opt_{len(options) + 1}"
        options.append({"value": value, "label": label})
        await state.update_data(new_question_options=options)
        options_text = "\n".join(f"  - {o['label']}" for o in options)
        await message.answer(
            f"Добавлено вариантов: {len(options)}\n{options_text}\n\n"
            "Введите метку следующего варианта или нажмите кнопку ниже:",
            reply_markup=add_option_keyboard(),
        )
    else:
        # Editing flow: switching type to choice. Build options list then save
        # on "options_done".
        options = data.get("pending_options", [])
        value = f"opt_{len(options) + 1}"
        options.append({"value": value, "label": label})
        await state.update_data(pending_options=options)
        options_text = "\n".join(f"  - {o['label']}" for o in options)
        await message.answer(
            f"Добавлено вариантов: {len(options)}\n{options_text}\n\n"
            "Введите метку следующего варианта или нажмите кнопку ниже:",
            reply_markup=add_option_keyboard(),
        )


@router.callback_query(
    SurveyEditFSM.adding_question_option,
    SurveyBuilderActionCB.filter(F.action == "options_done"),
)
async def cb_edit_options_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if data.get("new_question_title"):
        options = data.get("new_question_options", [])
        if len(options) < 2:
            await callback.answer("Нужно минимум 2 варианта")
            return
        await callback.answer()
        await _save_new_question(callback.message, state)
        return

    # Switching existing question type to choice
    options = data.get("pending_options", [])
    if len(options) < 2:
        await callback.answer("Нужно минимум 2 варианта")
        return
    question_id = data["edit_question_id"]
    new_type = data.get("pending_question_type")
    service = SurveyTemplateService()
    try:
        await service.update_question(question_id, question_type=new_type)
    except QuestionNotFoundError:
        await callback.answer("Вопрос не найден.")
        return
    await service.replace_question_options(question_id, options)
    await state.clear()
    await state.update_data(edit_question_id=question_id)
    await callback.answer()
    await _show_question_detail_cb(callback, question_id)


async def _save_new_question(message: Message, state: FSMContext):
    data = await state.get_data()
    template_id = data["edit_template_id"]
    qtype = data["new_question_type"]
    title = data["new_question_title"]

    config = None
    options = None
    if qtype == "rating":
        config = {
            "min": data.get("new_rating_min", 1),
            "max": data.get("new_rating_max", 10),
        }
    elif qtype in ("single_choice", "multiple_choice"):
        options = data.get("new_question_options", [])

    service = SurveyTemplateService()
    try:
        template = await service.get(template_id)
    except TemplateNotFoundError:
        await message.answer("Опрос не найден.")
        await state.clear()
        return

    next_order = len(template.questions) + 1
    await service.add_question(
        template_id=template_id,
        sort_order=next_order,
        title=title,
        question_type=qtype,
        config=config,
        options=options,
    )
    await state.clear()
    await state.update_data(edit_template_id=template_id)
    await _show_questions_list_msg(message, template_id)
