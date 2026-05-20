from aiogram.fsm.state import StatesGroup, State


class CohortTypeFSM(StatesGroup):
    waiting_type_name = State()
    waiting_option_name = State()
    waiting_rename_type = State()
    waiting_rename_option = State()
