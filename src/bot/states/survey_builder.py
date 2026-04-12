from aiogram.fsm.state import State, StatesGroup


class SurveyBuilderFSM(StatesGroup):
    entering_title = State()
    entering_description = State()
    adding_question_title = State()
    choosing_question_type = State()
    configuring_rating_min = State()
    configuring_rating_max = State()
    adding_option_label = State()


class SurveyEditFSM(StatesGroup):
    # Template fields
    editing_title = State()
    editing_description = State()
    editing_slug = State()
    # Question fields
    editing_question_title = State()
    choosing_question_type = State()
    editing_rating_min = State()
    editing_rating_max = State()
    # Options
    editing_option_label = State()
    adding_option_label = State()
    # Add new question to existing template
    adding_question_title = State()
    adding_question_type = State()
    adding_question_rating_min = State()
    adding_question_rating_max = State()
    adding_question_option = State()


class SurveySendFSM(StatesGroup):
    choosing_recipient_type = State()
    configuring_recipients = State()
    confirming = State()
