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


class SurveyResultsTemplateCB(CallbackData, prefix="sb_res_tmpl"):
    template_id: int


class SurveyResultsSessionCB(CallbackData, prefix="sb_res_sess"):
    session_id: int


class SurveySendSelectCB(CallbackData, prefix="ss_select"):
    template_id: int


class SurveySendRecipientCB(CallbackData, prefix="ss_rtype"):
    value: str


# --- Edit template / questions / options ---


class SurveyEditTemplateMenuCB(CallbackData, prefix="se_tmenu"):
    template_id: int


class SurveyEditFieldCB(CallbackData, prefix="se_field"):
    template_id: int
    field: str  # "title", "description", "slug"


class SurveyQuestionsListCB(CallbackData, prefix="se_qlist"):
    template_id: int


class SurveyEditQuestionCB(CallbackData, prefix="se_q"):
    question_id: int


class SurveyEditQFieldCB(CallbackData, prefix="se_qf"):
    question_id: int
    field: str  # "title", "type", "config", "options", "delete"


class SurveyAddQuestionCB(CallbackData, prefix="se_addq"):
    template_id: int


class SurveyEditOptionCB(CallbackData, prefix="se_opt"):
    option_id: int


class SurveyDeleteOptionCB(CallbackData, prefix="se_dopt"):
    option_id: int


class SurveyAddOptionCB(CallbackData, prefix="se_aopt"):
    question_id: int


class SurveyReorderQCB(CallbackData, prefix="se_reord"):
    question_id: int
    direction: str  # "up", "down"


class SurveyEditQuestionTypeCB(CallbackData, prefix="se_qtype"):
    question_id: int
    value: str
