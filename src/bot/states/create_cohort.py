from aiogram.fsm.state import State, StatesGroup


class CreateCohortFSM(StatesGroup):
    waiting_name = State()

