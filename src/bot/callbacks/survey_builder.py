from aiogram.filters.callback_data import CallbackData


class SurveyQuestionTypeCB(CallbackData, prefix="sq_type"):
    value: str


class SurveyBuilderActionCB(CallbackData, prefix="sb_action"):
    action: str


class SurveyTemplateDetailCB(CallbackData, prefix="sb_detail"):
    template_id: int


class SurveyTemplateToggleCB(CallbackData, prefix="sb_toggle"):
    template_id: int


class SurveyTemplateDeleteCB(CallbackData, prefix="sb_delete"):
    template_id: int
