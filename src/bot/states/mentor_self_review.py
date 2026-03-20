from aiogram.fsm.state import State, StatesGroup


class MentorSelfReviewFSM(StatesGroup):
    waiting_workload = State()
    waiting_pigeon_stupidity = State()
    waiting_avg_neuromutation = State()
    waiting_comment = State()
