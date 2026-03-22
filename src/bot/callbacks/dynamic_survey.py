from aiogram.filters.callback_data import CallbackData


class StartDynamicSurveyCB(CallbackData, prefix="ds_start"):
    session_id: int


class DynamicSurveyAnswerCB(CallbackData, prefix="ds_ans"):
    value: str
