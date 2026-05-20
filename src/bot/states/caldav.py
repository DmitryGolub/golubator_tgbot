from aiogram.fsm.state import State, StatesGroup


class CalDAVSetupFSM(StatesGroup):
    entering_base_url = State()
    entering_username = State()
    entering_password = State()
