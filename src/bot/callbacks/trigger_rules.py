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
