from aiogram.fsm.state import State, StatesGroup


class TriggerRuleBuilderFSM(StatesGroup):
    entering_name = State()
    choosing_trigger_type = State()
    choosing_action_type = State()
    configuring_action_text = State()
    choosing_survey_template = State()
    choosing_recipient_type = State()
    configuring_recipients = State()
    setting_delay = State()
