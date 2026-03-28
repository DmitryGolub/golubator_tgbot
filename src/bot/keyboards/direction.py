from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.direction import SaveDirectionsCB, ToggleDirectionCB
from src.models.cohort import Cohort


def direction_cohorts_keyboard(
    cohorts: list[Cohort],
    selected_ids: set[int],
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for c in cohorts:
        mark = "✅" if c.id in selected_ids else "❌"
        kb.button(
            text=f"{mark} {c.value}",
            callback_data=ToggleDirectionCB(cohort_id=c.id),
        )
    kb.button(text="💾 Сохранить", callback_data=SaveDirectionsCB())
    kb.button(text="❌ Отмена", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()
