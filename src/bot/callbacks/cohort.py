from aiogram.filters.callback_data import CallbackData


class DeleteCohortCB(CallbackData, prefix="cohort_del"):
    cohort_id: int

