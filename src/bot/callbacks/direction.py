from aiogram.filters.callback_data import CallbackData


class ToggleDirectionCB(CallbackData, prefix="dir_toggle"):
    cohort_id: int


class SaveDirectionsCB(CallbackData, prefix="dir_save"):
    pass
