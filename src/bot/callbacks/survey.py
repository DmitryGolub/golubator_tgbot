from aiogram.filters.callback_data import CallbackData


class StartSurveyCB(CallbackData, prefix="survey_start"):
    call_id: int


class SurveyDurationCB(CallbackData, prefix="survey_duration"):
    call_id: int
    option: str


class SurveyRatingCB(CallbackData, prefix="survey_rate"):
    call_id: int
    question: str
    value: int


class SurveyCommentSkipCB(CallbackData, prefix="survey_skip"):
    call_id: int
