from aiogram.filters.callback_data import CallbackData


class PageNavCB(CallbackData, prefix="page"):
    menu: str  # "users", "cohorts", "students", "mstats", "meetings", "mentors"
    page: int


class PageJumpCB(CallbackData, prefix="pjump"):
    menu: str


class PageSearchCB(CallbackData, prefix="psrch"):
    menu: str


class PageSearchResetCB(CallbackData, prefix="psrst"):
    menu: str
