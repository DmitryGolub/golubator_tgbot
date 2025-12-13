from aiogram.fsm.state import StatesGroup, State


class CreateMeetingFSM(StatesGroup):
    choosing_student = State()
    waiting_description = State()
    waiting_date = State()
    waiting_time = State()
    waiting_link = State()
