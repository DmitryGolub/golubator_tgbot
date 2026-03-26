from aiogram.filters.callback_data import CallbackData
from pydantic import field_validator


class StartDynamicSurveyCB(CallbackData, prefix="ds_start"):
    session_id: int


class DynamicSurveyAnswerCB(CallbackData, prefix="ds_ans"):
    value: str

    @field_validator("value")
    @classmethod
    def validate_length(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 50:
            raise ValueError("value too long for callback_data")
        return v
