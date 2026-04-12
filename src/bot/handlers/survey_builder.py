import logging
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext

from src.bot.callbacks.pagination import PageNavCB
from src.bot.callbacks.survey_builder import (
    SurveyBuilderActionCB,
    SurveyQuestionTypeCB,
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
    add_option_keyboard,
    after_question_keyboard,
    cancel_keyboard,
    question_type_keyboard,
    results_sessions_keyboard,
    results_templates_keyboard,
    survey_builder_menu_keyboard,
    survey_send_confirm_keyboard,
    survey_send_recipient_type_keyboard,
    survey_send_templates_keyboard,
    template_detail_keyboard,
    templates_list_keyboard,
)
from src.bot.pagination_search import filter_items
from src.bot.states.survey_builder import SurveyBuilderFSM, SurveySendFSM
from src.bot.utils import safe_edit_text
from src.dao.survey_session import SurveySessionDAO
from src.dao.user import UserDAO
from src.services.survey_session import SessionNotFoundError, SurveySessionService
from src.services.survey_template import (
    SlugAlreadyExistsError,
    SurveyTemplateService,
    TemplateNotFoundError,
)
from src.services.ui_text import UiTextService
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
    await safe_edit_text(
        callback,
        await UiTextService.get("survey.menu.title"),
        reply_markup=survey_builder_menu_keyboard(),
    )


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

    lines = ["<b>Список опросов:</b>\n"]
    for idx, t in enumerate(page_items):
        global_num = page * 6 + idx + 1
        status = "ON" if t.is_active else "OFF"
        desc = t.description or "—"
        lines.append(f"{global_num}. [{status}] {e(t.title)}\n   Описание: {e(desc)}")

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


@router.callback_query(SurveyTemplateDetailCB.filter())
async def cb_template_detail(
    callback: CallbackQuery, callback_data: SurveyTemplateDetailCB
):
    await callback.answer()
    service = SurveyTemplateService()
    try:
        template = await service.get(callback_data.template_id)
    except TemplateNotFoundError:
        await safe_edit_text(callback, "Опрос не найден")
        return
    except Exception:
        logger.exception("Unexpected error in cb_template_detail")
        await safe_edit_text(callback, "Произошла ошибка")
        return

    questions_text = ""
    for q in template.questions:
        type_label = QUESTION_TYPE_LABELS.get(
            q.question_type.value, q.question_type.value
        )
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

    await safe_edit_text(
        callback, text, reply_markup=template_detail_keyboard(template)
    )


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

    templates = await service.list_active()
    if templates:
        text, markup = await _build_surveys_list_page(page=0)
        await safe_edit_text(callback, text, reply_markup=markup)
    else:
        await safe_edit_text(
            callback,
            await UiTextService.get("survey.menu.title"),
            reply_markup=survey_builder_menu_keyboard(),
        )


# --- Create template FSM ---


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "create"))
async def cb_start_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(SurveyBuilderFSM.entering_title)
    await callback.answer()
    await safe_edit_text(
        callback,
        "Введите название опроса:",
        reply_markup=cancel_keyboard(),
    )


@router.message(SurveyBuilderFSM.entering_title)
async def msg_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Название не может быть пустым. Попробуйте снова:")
        return

    slug = uuid.uuid4().hex[:12]
    await state.update_data(title=title, slug=slug, questions=[])
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

    await safe_edit_text(
        callback,
        f"Опрос <b>{template.title}</b> создан.\n"
        f"Slug: <code>{template.slug}</code>\n"
        f"Вопросов: {len(template.questions)}{questions_text}",
        reply_markup=survey_builder_menu_keyboard(),
    )


# --- Results ---


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "results"))
async def cb_results_templates(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    service = SurveyTemplateService()
    templates = await service.list_active()
    if not templates:
        await safe_edit_text(callback, "Нет опросов")
        return

    await safe_edit_text(
        callback,
        "Выберите опрос для просмотра результатов:",
        reply_markup=results_templates_keyboard(templates),
    )


@router.callback_query(SurveyResultsTemplateCB.filter())
async def cb_results_sessions(
    callback: CallbackQuery, callback_data: SurveyResultsTemplateCB
):
    await callback.answer()
    sessions = await SurveySessionDAO.get_completed_by_template(
        callback_data.template_id
    )
    if not sessions:
        await safe_edit_text(
            callback,
            "Завершённых сессий нет.",
            reply_markup=survey_builder_menu_keyboard(),
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
        await safe_edit_text(
            callback,
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
            if q and q.options:
                label_map = {opt.value: opt.label for opt in q.options}
                val = ", ".join(label_map.get(v, v) for v in answer.value_choice)
            else:
                val = ", ".join(answer.value_choice)
        else:
            val = "—"
        lines.append(f"<b>{q_title}</b>\n  {val}")

    await safe_edit_text(
        callback,
        "\n".join(lines),
        reply_markup=survey_builder_menu_keyboard(),
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


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "send"))
async def cb_send_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    service = SurveyTemplateService()
    templates = await service.list_active()

    if not templates:
        await safe_edit_text(
            callback,
            "Нет активных опросов для отправки.",
            reply_markup=survey_builder_menu_keyboard(),
        )
        return

    await safe_edit_text(
        callback,
        "Выберите опрос для отправки:",
        reply_markup=survey_send_templates_keyboard(templates),
    )


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
    await safe_edit_text(
        callback,
        f"Опрос <b>{e(template_title)}</b> отправлен.\nПолучателей: <b>{sent}</b>",
        reply_markup=survey_builder_menu_keyboard(),
    )


# --- Cancel ---


@router.callback_query(SurveyBuilderActionCB.filter(F.action == "cancel"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    await safe_edit_text(
        callback,
        await UiTextService.get("survey.menu.title"),
        reply_markup=survey_builder_menu_keyboard(),
    )
