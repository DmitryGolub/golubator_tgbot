from aiogram.fsm.state import State, StatesGroup


class DynamicSurveyFSM(StatesGroup):
    answering = State()
    waiting_text = State()
