from aiogram.fsm.state import State, StatesGroup


class CreateTagFSM(StatesGroup):
    waiting_name = State()
