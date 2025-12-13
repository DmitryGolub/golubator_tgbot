from aiogram.filters.callback_data import CallbackData


class ChooseMeetingStudentCB(CallbackData, prefix="meeting_student"):
    student_id: int


class DeleteMeetingCB(CallbackData, prefix="meeting_del"):
    meeting_id: int


class ChooseMeetingDateCB(CallbackData, prefix="meeting_date"):
    year: int
    month: int
    day: int


class NavigateMeetingMonthCB(CallbackData, prefix="meeting_nav"):
    year: int
    month: int
    delta: int  # +1 or -1


class ChooseMeetingTimeCB(CallbackData, prefix="meeting_time"):
    t: str  # HHMM
