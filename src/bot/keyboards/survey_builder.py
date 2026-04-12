from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
from src.bot.keyboards.pagination import DEFAULT_PAGE_SIZE, build_paginated_keyboard
from src.models.survey_session import SurveySession
from src.models.survey_template import SurveyTemplate


QUESTION_TYPE_LABELS = {
    "text": "Текст",
    "rating": "Рейтинг (число)",
    "single_choice": "Одиночный выбор",
    "multiple_choice": "Множественный выбор",
}


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
        back_button=InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_surveys"),
    )


def template_detail_keyboard(template: SurveyTemplate) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "Выключить" if template.is_active else "Включить"
    builder.button(
        text=toggle_text, callback_data=SurveyTemplateToggleCB(template_id=template.id)
    )
    builder.button(
        text="Удалить", callback_data=SurveyTemplateDeleteCB(template_id=template.id)
    )
    builder.button(text="⬅️ Назад", callback_data=SurveyBuilderActionCB(action="list"))
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
