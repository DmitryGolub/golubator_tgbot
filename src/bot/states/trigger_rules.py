from aiogram.fsm.state import State, StatesGroup


class TriggerRuleBuilderFSM(StatesGroup):
    entering_name = State()
    choosing_trigger_type = State()
    choosing_schedule_mode = State()
    entering_cron_expression = State()
    choosing_regularity = State()
    entering_time_of_day = State()
    choosing_action_type = State()
    configuring_action_text = State()
    choosing_survey_template = State()
    choosing_recipient_type = State()
    choosing_cohort_type = State()
    choosing_cohort_from = State()
    choosing_cohort_to = State()
    configuring_recipients = State()
    setting_delay = State()


class TriggerRuleEditFSM(StatesGroup):
    choosing_field = State()
    editing_name = State()
    editing_trigger_type = State()
    editing_action_type = State()
    editing_recipient_type = State()
    editing_cron = State()
    editing_regularity = State()
    editing_time_of_day = State()
    editing_delay = State()
    editing_delay_mode = State()
    editing_action_text = State()
    editing_survey_template = State()
    editing_recipient_config = State()
    editing_cohort_type = State()
    editing_cohort_from = State()
    editing_cohort_to = State()
