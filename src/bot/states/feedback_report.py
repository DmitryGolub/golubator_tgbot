from aiogram.fsm.state import State, StatesGroup


class FeedbackReportFSM(StatesGroup):
    choosing_type = State()
    entering_text = State()
    choosing_recipient = State()
