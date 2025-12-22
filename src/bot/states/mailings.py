from aiogram.fsm.state import State, StatesGroup


class MailingFSM(StatesGroup):
    choosing_type = State()
    waiting_title = State()

    choosing_users = State()
    choosing_states = State()
    choosing_cohorts = State()

    waiting_text = State()
    choosing_regularity = State()

    deleting_rules = State()
