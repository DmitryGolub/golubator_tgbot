from aiogram.fsm.state import StatesGroup, State


class UpdateUserFSM(StatesGroup):
    choosing_param = State()
    choosing_value = State()
    choosing_user = State()
