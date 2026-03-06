from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.survey import (
    StartSurveyCB,
    SurveyCommentSkipCB,
    SurveyDurationCB,
    SurveyRatingCB,
)
from src.survey.constants import DURATION_OPTION_LABELS


def survey_start_keyboard(call_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📝 Оставить обратную связь",
        callback_data=StartSurveyCB(call_id=call_id).pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def survey_duration_keyboard(call_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for option, label in DURATION_OPTION_LABELS.items():
        kb.button(
            text=label,
            callback_data=SurveyDurationCB(call_id=call_id, option=option.value).pack(),
        )

    kb.button(text="❌ Отмена", callback_data="survey_cancel")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def survey_rating_keyboard(call_id: int, question: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for value in range(1, 6):
        kb.button(
            text=str(value),
            callback_data=SurveyRatingCB(call_id=call_id, question=question, value=value).pack(),
        )

    kb.button(text="❌ Отмена", callback_data="survey_cancel")
    kb.adjust(5, 1)
    return kb.as_markup()


def survey_comment_keyboard(call_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Пропустить комментарий",
        callback_data=SurveyCommentSkipCB(call_id=call_id).pack(),
    )
    kb.button(text="❌ Отмена", callback_data="survey_cancel")
    kb.adjust(1)
    return kb.as_markup()
