from aiogram.filters.callback_data import CallbackData


class PageNavCB(CallbackData, prefix="page"):
    menu: str  # "users", "cohorts", "students", "mstats", "meetings", "mentors"
    page: int
