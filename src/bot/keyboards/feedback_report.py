from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.feedback_report import (
    FeedbackRecipientCB,
    FeedbackSkipPhotoCB,
    FeedbackTypeCB,
)


def feedback_type_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Проблема или предложение", callback_data=FeedbackTypeCB(value="problem")
    )
    kb.button(text="Баг-репорт", callback_data=FeedbackTypeCB(value="bug"))
    kb.button(text="⬅️ Назад", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def feedback_recipient_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Координатор", callback_data=FeedbackRecipientCB(role="admin"))
    kb.button(
        text="Лид направления",
        callback_data=FeedbackRecipientCB(role="direction_lead"),
    )
    kb.button(
        text="Лид по сопровождению",
        callback_data=FeedbackRecipientCB(role="education_lead"),
    )
    kb.button(
        text="Лид по поиску работы",
        callback_data=FeedbackRecipientCB(role="job_search_lead"),
    )
    kb.button(text="❌ Отмена", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def feedback_skip_photo_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустить", callback_data=FeedbackSkipPhotoCB())
    kb.button(text="❌ Отмена", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()
