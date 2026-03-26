from aiogram.filters.callback_data import CallbackData


class TriggerActionCB(CallbackData, prefix="tr_action"):
    action: str


class TriggerTypeCB(CallbackData, prefix="tr_type"):
    value: str


class TriggerActionTypeCB(CallbackData, prefix="tr_atype"):
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


class TriggerRuleSendCB(CallbackData, prefix="tr_send"):
    rule_id: int


class TriggerSurveyTemplateCB(CallbackData, prefix="tr_survey"):
    template_id: int
