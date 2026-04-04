from aiogram.fsm.state import StatesGroup, State


class FeedbackReportFSM(StatesGroup):
    choosing_type = State()
    entering_text = State()
    choosing_recipient = State()
    waiting_photo = State()
