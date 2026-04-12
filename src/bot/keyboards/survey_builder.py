from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
from src.bot.keyboards.pagination import DEFAULT_PAGE_SIZE, build_paginated_keyboard
from src.models.survey_session import SurveySession
from src.models.survey_template import SurveyQuestion, SurveyTemplate


QUESTION_TYPE_LABELS = {
    "text": "Текст",
    "rating": "Рейтинг (число)",
    "single_choice": "Одиночный выбор",
    "multiple_choice": "Множественный выбор",
}

TEMPLATE_KIND_LABELS = {
    "survey": "Опрос",
    "broadcast": "Рассылка",
}


def template_kind_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📝 Опрос (с вопросами)",
        callback_data=SurveyBuilderActionCB(action="kind_survey"),
    )
    builder.button(
        text="📢 Рассылка (только текст)",
        callback_data=SurveyBuilderActionCB(action="kind_broadcast"),
    )
    builder.button(
        text="❌ Отмена", callback_data=SurveyBuilderActionCB(action="cancel")
    )
    builder.adjust(1)
    return builder.as_markup()


def survey_builder_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Создать опрос", callback_data=SurveyBuilderActionCB(action="create")
    )
    builder.button(
        text="Список опросов", callback_data=SurveyBuilderActionCB(action="list")
    )
    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def question_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in QUESTION_TYPE_LABELS.items():
        builder.button(text=label, callback_data=SurveyQuestionTypeCB(value=value))
    builder.button(
        text="❌ Отмена", callback_data=SurveyBuilderActionCB(action="cancel")
    )
    builder.adjust(1)
    return builder.as_markup()


def after_question_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Добавить ещё вопрос",
        callback_data=SurveyBuilderActionCB(action="add_question"),
    )
    builder.button(
        text="Завершить создание", callback_data=SurveyBuilderActionCB(action="finish")
    )
    builder.button(
        text="❌ Отмена", callback_data=SurveyBuilderActionCB(action="cancel")
    )
    builder.adjust(1)
    return builder.as_markup()


def add_option_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Закончить добавление вариантов",
        callback_data=SurveyBuilderActionCB(action="options_done"),
    )
    builder.button(
        text="❌ Отмена", callback_data=SurveyBuilderActionCB(action="cancel")
    )
    builder.adjust(1)
    return builder.as_markup()


def templates_list_keyboard(
    templates: list[SurveyTemplate],
    page: int = 0,
    total_pages: int = 1,
    search_query: str | None = None,
) -> InlineKeyboardMarkup:
    item_buttons = []
    for idx, t in enumerate(templates):
        num = page * DEFAULT_PAGE_SIZE + idx + 1
        item_buttons.append(
            InlineKeyboardButton(
                text=f"Изменить #{num}",
                callback_data=SurveyTemplateDetailCB(template_id=t.id).pack(),
            )
        )
        item_buttons.append(
            InlineKeyboardButton(
                text=f"📊 #{num}",
                callback_data=SurveyResultsTemplateCB(template_id=t.id).pack(),
            )
        )
        item_buttons.append(
            InlineKeyboardButton(
                text=f"Отправить #{num}",
                callback_data=SurveySendSelectCB(template_id=t.id).pack(),
            )
        )
    return build_paginated_keyboard(
        menu="surveys_list",
        page=page,
        total_pages=total_pages,
        item_buttons=item_buttons,
        columns=3,
        search_query=search_query,
        extra_rows=[
            [
                InlineKeyboardButton(
                    text="Создать опрос",
                    callback_data=SurveyBuilderActionCB(action="create").pack(),
                )
            ]
        ],
        back_button=InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"),
    )


def template_detail_keyboard(template: SurveyTemplate) -> InlineKeyboardMarkup:
    from src.models.survey_template import TemplateKind

    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Редактировать",
        callback_data=SurveyEditTemplateMenuCB(template_id=template.id),
    )
    is_broadcast = template.kind == TemplateKind.broadcast
    if not is_broadcast:
        builder.button(
            text="📝 Вопросы",
            callback_data=SurveyQuestionsListCB(template_id=template.id),
        )
    toggle_text = "Выключить" if template.is_active else "Включить"
    builder.button(
        text=toggle_text, callback_data=SurveyTemplateToggleCB(template_id=template.id)
    )
    builder.button(
        text="Удалить", callback_data=SurveyTemplateDeleteCB(template_id=template.id)
    )
    builder.button(text="⬅️ Назад", callback_data=SurveyBuilderActionCB(action="list"))
    if is_broadcast:
        builder.adjust(1, 2, 1)
    else:
        builder.adjust(2, 2, 1)
    return builder.as_markup()


def edit_template_fields_keyboard(
    template_id: int, is_broadcast: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Название",
        callback_data=SurveyEditFieldCB(template_id=template_id, field="title"),
    )
    if is_broadcast:
        builder.button(
            text="Текст рассылки",
            callback_data=SurveyEditFieldCB(template_id=template_id, field="body"),
        )
    else:
        builder.button(
            text="Описание",
            callback_data=SurveyEditFieldCB(
                template_id=template_id, field="description"
            ),
        )
    builder.button(
        text="Slug",
        callback_data=SurveyEditFieldCB(template_id=template_id, field="slug"),
    )
    builder.button(
        text="⬅️ Назад",
        callback_data=SurveyTemplateDetailCB(template_id=template_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def questions_list_keyboard(template: SurveyTemplate) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for q in template.questions:
        builder.button(
            text=f"{q.sort_order}. {q.title[:40]}",
            callback_data=SurveyEditQuestionCB(question_id=q.id),
        )
    builder.button(
        text="➕ Добавить вопрос",
        callback_data=SurveyAddQuestionCB(template_id=template.id),
    )
    builder.button(
        text="⬅️ Назад",
        callback_data=SurveyTemplateDetailCB(template_id=template.id),
    )
    builder.adjust(1)
    return builder.as_markup()


def edit_question_keyboard(question: SurveyQuestion) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Текст",
        callback_data=SurveyEditQFieldCB(question_id=question.id, field="title"),
    )
    builder.button(
        text="🔀 Тип",
        callback_data=SurveyEditQFieldCB(question_id=question.id, field="type"),
    )
    qtype = (
        question.question_type.value
        if hasattr(question.question_type, "value")
        else question.question_type
    )
    if qtype == "rating":
        builder.button(
            text="🔢 Рейтинг",
            callback_data=SurveyEditQFieldCB(question_id=question.id, field="config"),
        )
    elif qtype in ("single_choice", "multiple_choice"):
        builder.button(
            text="📋 Варианты",
            callback_data=SurveyEditQFieldCB(question_id=question.id, field="options"),
        )
    builder.button(
        text="⬆️",
        callback_data=SurveyReorderQCB(question_id=question.id, direction="up"),
    )
    builder.button(
        text="⬇️",
        callback_data=SurveyReorderQCB(question_id=question.id, direction="down"),
    )
    builder.button(
        text="🗑 Удалить вопрос",
        callback_data=SurveyEditQFieldCB(question_id=question.id, field="delete"),
    )
    builder.button(
        text="⬅️ Назад",
        callback_data=SurveyQuestionsListCB(template_id=question.template_id),
    )
    builder.adjust(2, 1, 2, 1, 1)
    return builder.as_markup()


def edit_options_keyboard(question: SurveyQuestion) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt in question.options:
        builder.button(
            text=f"✏️ {opt.label[:30]}",
            callback_data=SurveyEditOptionCB(option_id=opt.id),
        )
        builder.button(
            text="🗑",
            callback_data=SurveyDeleteOptionCB(option_id=opt.id),
        )
    builder.button(
        text="➕ Добавить вариант",
        callback_data=SurveyAddOptionCB(question_id=question.id),
    )
    builder.button(
        text="⬅️ Назад",
        callback_data=SurveyEditQuestionCB(question_id=question.id),
    )
    # 2 columns for the option pairs, then single column for add/back
    sizes = [2] * len(question.options) + [1, 1]
    builder.adjust(*sizes)
    return builder.as_markup()


def question_type_edit_keyboard(question_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in QUESTION_TYPE_LABELS.items():
        builder.button(
            text=label,
            callback_data=SurveyEditQuestionTypeCB(
                question_id=question_id, value=value
            ),
        )
    builder.button(
        text="⬅️ Назад",
        callback_data=SurveyEditQuestionCB(question_id=question_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def results_sessions_keyboard(sessions: list[SurveySession]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in sessions:
        date_str = s.completed_at.strftime("%d.%m.%Y %H:%M") if s.completed_at else "—"
        builder.button(
            text=f"#{s.id} ({date_str})",
            callback_data=SurveyResultsSessionCB(session_id=s.id),
        )
    builder.button(text="⬅️ Назад", callback_data=SurveyBuilderActionCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


def survey_send_recipient_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="По роли", callback_data=SurveySendRecipientCB(value="by_role"))
    builder.button(
        text="По статусу", callback_data=SurveySendRecipientCB(value="by_state")
    )
    builder.button(
        text="По когорте", callback_data=SurveySendRecipientCB(value="by_cohort")
    )
    builder.button(
        text="Конкретные пользователи",
        callback_data=SurveySendRecipientCB(value="specific_users"),
    )
    builder.button(
        text="❌ Отмена", callback_data=SurveyBuilderActionCB(action="cancel")
    )
    builder.adjust(1)
    return builder.as_markup()


def survey_send_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Отправить",
        callback_data=SurveyBuilderActionCB(action="send_confirm"),
    )
    builder.button(
        text="❌ Отмена", callback_data=SurveyBuilderActionCB(action="cancel")
    )
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Отмена", callback_data=SurveyBuilderActionCB(action="cancel")
    )
    builder.adjust(1)
    return builder.as_markup()
