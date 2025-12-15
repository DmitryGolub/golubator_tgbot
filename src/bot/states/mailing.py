from aiogram.fsm.state import StatesGroup, State


class MailingFSM(StatesGroup):
    choosing_type = State()
    waiting_name = State()
    choosing_users = State()
    choosing_states = State()
    waiting_text = State()
    choosing_regularity = State()
