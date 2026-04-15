from aiogram.filters.callback_data import CallbackData


class TriggerActionCB(CallbackData, prefix="tr_action"):
    action: str


class TriggerTypeCB(CallbackData, prefix="tr_type"):
    value: str


class TriggerRecipientTypeCB(CallbackData, prefix="tr_rtype"):
    value: str


class TriggerRuleDetailCB(CallbackData, prefix="tr_detail"):
    rule_id: int


class TriggerRuleToggleCB(CallbackData, prefix="tr_toggle"):
    rule_id: int


class TriggerRuleDeleteCB(CallbackData, prefix="tr_delete"):
    rule_id: int


class TriggerRuleConfirmDeleteCB(CallbackData, prefix="tr_cdel"):
    rule_id: int


class TriggerRuleFireCB(CallbackData, prefix="tr_fire"):
    rule_id: int


class TriggerRuleFireConfirmCB(CallbackData, prefix="tr_cfire"):
    rule_id: int


class TriggerSurveyTemplateCB(CallbackData, prefix="tr_survey"):
    template_id: int


class TriggerScheduleModeCB(CallbackData, prefix="tr_smode"):
    value: str


class TriggerRegularityCB(CallbackData, prefix="tr_reg"):
    value: str


class TriggerCohortTypeCB(CallbackData, prefix="tr_ctype"):
    value: str


class TriggerCohortValueCB(CallbackData, prefix="tr_cval"):
    value: str


class TriggerRuleEditMenuCB(CallbackData, prefix="tr_edm"):
    rule_id: int


class TriggerRuleEditFieldCB(CallbackData, prefix="tr_edf"):
    field: str


class TriggerDelayModeCB(CallbackData, prefix="tr_dmd"):
    value: str


class TriggerPickRoleCB(CallbackData, prefix="tr_pick_role"):
    role_id: int


class TriggerPickStateCB(CallbackData, prefix="tr_pick_state"):
    value: str


class TriggerPickCohortTypeCB(CallbackData, prefix="tr_pick_ct"):
    type: str


class TriggerPickCohortValueCB(CallbackData, prefix="tr_pick_cv"):
    value: str


class TriggerPickUserCB(CallbackData, prefix="tr_pick_user"):
    telegram_id: int


class TriggerUsersDoneCB(CallbackData, prefix="tr_users_done"):
    pass


class TriggerRecipientPageCB(CallbackData, prefix="tr_rpage"):
    kind: str
    page: int


class TriggerRecipientBackCB(CallbackData, prefix="tr_rback"):
    step: str


class TriggerTimeHourCB(CallbackData, prefix="tr_thour"):
    hour: int


class TriggerTimeMinuteCB(CallbackData, prefix="tr_tmin"):
    minute: int


class TriggerTimeBackCB(CallbackData, prefix="tr_tback"):
    pass


class TriggerDelayPresetCB(CallbackData, prefix="tr_dprst"):
    seconds: int
