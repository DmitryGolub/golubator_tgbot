from aiogram.filters.callback_data import CallbackData


class ChooseFeedbackMeetingCB(CallbackData, prefix="feedback_meeting"):
    meeting_id: int


class ChooseFeedbackStatusCB(CallbackData, prefix="feedback_status"):
    value: str


class ChooseFeedbackDurationCB(CallbackData, prefix="feedback_duration"):
    value: str
