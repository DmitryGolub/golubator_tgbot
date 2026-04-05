from enum import StrEnum
from aiogram.filters.callback_data import CallbackData


class UpdateParam(StrEnum):
    STATUS = "status"
    ROLE = "role"
    MENTOR = "mentor"
    COHORT = "cohort"


# выбор, ЧТО меняем (статус/роль/ментор)
class ChooseParamCB(CallbackData, prefix="upd_param"):
    param: UpdateParam


# выбор значения для enum (роль / статус)
class ChooseEnumValueCB(CallbackData, prefix="upd_enum"):
    param: UpdateParam  # STATUS или ROLE
    value: str  # значение enum'а (value)


# выбор ментора
class ChooseMentorCB(CallbackData, prefix="upd_mentor"):
    mentor_id: int


# выбор пользователя, к которому применяем изменение
class ChooseUserCB(CallbackData, prefix="upd_user"):
    user_id: int


# выбор менти по Mentee.id (PK) — для менти без telegram_id
class ChooseMenteeCB(CallbackData, prefix="upd_mentee"):
    mentee_id: int


# выбор типа когорты (Category, Stream, etc.)
class ChooseCohortTypeCB(CallbackData, prefix="upd_ctype"):
    cohort_type: str


# cancel update flow
class CancelUpdateCB(CallbackData, prefix="upd_cancel"):
    pass
