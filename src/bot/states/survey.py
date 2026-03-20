from aiogram.fsm.state import State, StatesGroup


class SurveyFSM(StatesGroup):
    choosing_duration = State()
    rating_mentor_style = State()
    rating_knowledge_depth = State()
    rating_understanding = State()
    waiting_comment = State()
