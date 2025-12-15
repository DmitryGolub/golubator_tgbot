from aiogram.filters.callback_data import CallbackData

from src.models.user import State
from src.models.rule import Regularity


class MailingTypeCB(CallbackData, prefix="mail_type"):
    kind: str  # user or state


class MailingUserSelectCB(CallbackData, prefix="mail_user"):
    user_id: int


class MailingStateSelectCB(CallbackData, prefix="mail_state"):
    state: State


class MailingRegularityCB(CallbackData, prefix="mail_reg"):
    regularity: Regularity
