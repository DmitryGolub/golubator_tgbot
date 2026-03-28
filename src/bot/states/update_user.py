from aiogram.fsm.state import StatesGroup, State


class UpdateUserFSM(StatesGroup):
    choosing_param = State()
    choosing_cohort_type = State()
    choosing_value = State()
    choosing_user = State()
