from enum import StrEnum
from aiogram.filters.callback_data import CallbackData

from src.models.user import Role, State


class UpdateParam(StrEnum):
    STATUS = "status"
    ROLE = "role"
    MENTOR = "mentor"
    COHORT = "cohort"


# выбор, ЧТО меняем (статус/роль/ментор/когорта)
class ChooseParamCB(CallbackData, prefix="upd_param"):
    param: UpdateParam


# выбор значения для enum (роль / статус)
class ChooseEnumValueCB(CallbackData, prefix="upd_enum"):
    param: UpdateParam          # STATUS или ROLE
    value: str                  # значение enum'а (value)


# выбор ментора
class ChooseMentorCB(CallbackData, prefix="upd_mentor"):
    mentor_id: int


# выбор когорты
class ChooseCohortCB(CallbackData, prefix="upd_cohort"):
    cohort_id: int


# выбор пользователя, к которому применяем изменение
class ChooseUserCB(CallbackData, prefix="upd_user"):
    user_id: int
