from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from src.bot.callbacks.cohort import DeleteCohortCB
from src.models.cohort import Cohort


def cohort_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Список когорт", callback_data="cohort_list")
    kb.button(text="Добавить когорту", callback_data="cohort_create")
    kb.button(text="Удалить когорту", callback_data="cohort_delete")

    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")

    kb.adjust(1)

    return kb.as_markup()


def cohort_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Отмена", callback_data="cohort_create_cancel")

    kb.adjust(1)

    return kb.as_markup()


def cohort_delete_keyboard(cohorts: list[Cohort]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for cohort in cohorts:
        kb.button(
            text=cohort.name,
            callback_data=DeleteCohortCB(cohort_id=cohort.id).pack(),
        )

    kb.adjust(1)

    return kb.as_markup()