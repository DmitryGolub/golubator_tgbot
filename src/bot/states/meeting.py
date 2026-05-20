from aiogram.fsm.state import StatesGroup, State


class CreateMeetingFSM(StatesGroup):
    choosing_student = State()
    choosing_type = State()
    waiting_description = State()
    waiting_date = State()
    waiting_time = State()
    waiting_link = State()


class ApproveMeetingFSM(StatesGroup):
    entering_link = State()


class EditMeetingFSM(StatesGroup):
    choosing_field = State()
    editing_datetime_date = State()
    editing_datetime_time = State()
    editing_description = State()
    editing_link = State()
    editing_type = State()
    editing_student = State()
