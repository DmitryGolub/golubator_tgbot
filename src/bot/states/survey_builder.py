from aiogram.fsm.state import State, StatesGroup


class SurveyBuilderFSM(StatesGroup):
    entering_title = State()
    entering_description = State()
    adding_question_title = State()
    choosing_question_type = State()
    configuring_rating_min = State()
    configuring_rating_max = State()
    adding_option_label = State()


class SurveySendFSM(StatesGroup):
    choosing_recipient_type = State()
    configuring_recipients = State()
    confirming = State()
