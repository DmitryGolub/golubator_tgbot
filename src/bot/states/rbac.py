from aiogram.fsm.state import State, StatesGroup


class CreateRoleFSM(StatesGroup):
    waiting_name = State()
    waiting_display_name = State()
