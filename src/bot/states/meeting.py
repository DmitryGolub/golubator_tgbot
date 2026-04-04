from aiogram.fsm.state import StatesGroup, State


class CreateMeetingFSM(StatesGroup):
    choosing_student = State()
    choosing_type = State()
    waiting_description = State()
    waiting_date = State()
    waiting_time = State()
    waiting_link = State()


class RescheduleMeetingFSM(StatesGroup):
    waiting_date = State()
    waiting_time = State()
    waiting_link = State()
