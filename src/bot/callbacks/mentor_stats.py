from aiogram.filters.callback_data import CallbackData


class MentorStatsCB(CallbackData, prefix="mstats"):
    mentor_id: int
