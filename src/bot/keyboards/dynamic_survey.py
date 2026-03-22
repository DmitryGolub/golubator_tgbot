from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.dynamic_survey import DynamicSurveyAnswerCB
from src.models.survey_template import QuestionType, SurveyQuestion


def render_question_keyboard(question: SurveyQuestion) -> InlineKeyboardMarkup | None:
    if question.question_type == QuestionType.text:
        return None

    builder = InlineKeyboardBuilder()

    if question.question_type == QuestionType.rating:
        config = question.config or {}
        min_val = config.get("min", 1)
        max_val = config.get("max", 5)
        for i in range(min_val, max_val + 1):
            builder.button(
                text=str(i),
                callback_data=DynamicSurveyAnswerCB(value=str(i)),
            )
        builder.adjust(5)

    elif question.question_type == QuestionType.single_choice:
        for opt in question.options:
            builder.button(
                text=opt.label,
                callback_data=DynamicSurveyAnswerCB(value=opt.value),
            )
        builder.adjust(1)

    elif question.question_type == QuestionType.multiple_choice:
        for opt in question.options:
            builder.button(
                text=opt.label,
                callback_data=DynamicSurveyAnswerCB(value=opt.value),
            )
        builder.button(
            text="Готово",
            callback_data=DynamicSurveyAnswerCB(value="__done__"),
        )
        builder.adjust(1)

    builder.button(
        text="Отмена",
        callback_data=DynamicSurveyAnswerCB(value="__cancel__"),
    )

    return builder.as_markup()
