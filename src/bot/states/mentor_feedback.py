from aiogram.fsm.state import State, StatesGroup


class MentorFeedbackFSM(StatesGroup):
    choosing_meeting = State()
    choosing_status = State()
    choosing_duration = State()
    waiting_motivation = State()
    waiting_neuromutation_stage = State()
    waiting_comment = State()
