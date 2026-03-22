from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.survey_builder import (
    SurveyBuilderActionCB,
    SurveyQuestionTypeCB,
    SurveyTemplateDeleteCB,
    SurveyTemplateDetailCB,
    SurveyTemplateToggleCB,
)
from src.models.survey_template import SurveyTemplate


QUESTION_TYPE_LABELS = {
    "text": "Текст",
    "rating": "Рейтинг (число)",
    "single_choice": "Одиночный выбор",
    "multiple_choice": "Множественный выбор",
}


def survey_builder_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Создать опрос", callback_data=SurveyBuilderActionCB(action="create"))
    builder.button(text="Список опросов", callback_data=SurveyBuilderActionCB(action="list"))
    builder.button(text="Назад", callback_data="menu_back")
    builder.adjust(1)
    return builder.as_markup()


def question_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in QUESTION_TYPE_LABELS.items():
        builder.button(text=label, callback_data=SurveyQuestionTypeCB(value=value))
    builder.button(text="Отмена", callback_data=SurveyBuilderActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def after_question_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить ещё вопрос", callback_data=SurveyBuilderActionCB(action="add_question"))
    builder.button(text="Завершить создание", callback_data=SurveyBuilderActionCB(action="finish"))
    builder.button(text="Отмена", callback_data=SurveyBuilderActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def add_option_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Закончить добавление вариантов", callback_data=SurveyBuilderActionCB(action="options_done"))
    builder.button(text="Отмена", callback_data=SurveyBuilderActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def templates_list_keyboard(templates: list[SurveyTemplate]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in templates:
        status = "ON" if t.is_active else "OFF"
        builder.button(
            text=f"[{status}] {t.title}",
            callback_data=SurveyTemplateDetailCB(template_id=t.id),
        )
    builder.button(text="Назад", callback_data="menu_surveys")
    builder.adjust(1)
    return builder.as_markup()


def template_detail_keyboard(template: SurveyTemplate) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "Выключить" if template.is_active else "Включить"
    builder.button(text=toggle_text, callback_data=SurveyTemplateToggleCB(template_id=template.id))
    builder.button(text="Удалить", callback_data=SurveyTemplateDeleteCB(template_id=template.id))
    builder.button(text="Назад", callback_data=SurveyBuilderActionCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data=SurveyBuilderActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()
