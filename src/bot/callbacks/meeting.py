from aiogram.filters.callback_data import CallbackData


class ChooseMeetingStudentCB(CallbackData, prefix="meeting_student"):
    mentee_id: int


class DeleteMeetingCB(CallbackData, prefix="meeting_del"):
    meeting_id: int


class StartMeetingCallCB(CallbackData, prefix="meeting_start_call"):
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


class ChooseMeetingTypeCB(CallbackData, prefix="meeting_type"):
    type_idx: int


class ConfirmMeetingCB(CallbackData, prefix="mtg_confirm"):
    meeting_id: int


class DeclineMeetingCB(CallbackData, prefix="mtg_decline"):
    meeting_id: int


class ProposeNewTimeCB(CallbackData, prefix="mtg_newtime"):
    meeting_id: int  # исходная встреча


class RequestRescheduleCB(CallbackData, prefix="mtg_reschedule"):
    meeting_id: int  # подтверждённая встреча для переноса
