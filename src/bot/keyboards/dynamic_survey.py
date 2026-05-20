from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
from src.models.survey_session import SurveySession


def my_surveys_keyboard(sessions: list[SurveySession]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in sessions:
        kb.row(
            InlineKeyboardButton(
                text=s.template.title,
                callback_data=StartDynamicSurveyCB(session_id=s.id).pack(),
            )
        )
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
    return kb.as_markup()
