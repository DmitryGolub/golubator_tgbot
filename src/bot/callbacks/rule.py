from aiogram.filters.callback_data import CallbackData

from src.models.user import State
from src.models.rule import Regularity


class MailingTypeCB(CallbackData, prefix="mailing_type"):
    kind: str  # individual | state


class ToggleUserCB(CallbackData, prefix="mail_user"):
    user_id: int


class ToggleStateCB(CallbackData, prefix="mail_state"):
    state: State


class ChooseRegularityCB(CallbackData, prefix="mail_reg"):
    regularity: Regularity


class MailingFinishUsersCB(CallbackData, prefix="mail_finish_users"):
    done: bool


class MailingFinishStatesCB(CallbackData, prefix="mail_finish_states"):
    done: bool


class ToggleDeleteUserRuleCB(CallbackData, prefix="mail_del_user"):
    rule_id: int


class ToggleDeleteStateRuleCB(CallbackData, prefix="mail_del_state"):
    rule_id: int


class DeleteMailingsFinishCB(CallbackData, prefix="mail_del_finish"):
    done: bool
