from enum import Enum

from aiogram.filters.callback_data import CallbackData

class UserAction(str, Enum):
    update_role = "update_role"
    update_state = "update_state"
    update_mentor = "update_mentor"


class UserActionSelectCB(CallbackData, prefix="uact"):
    action: UserAction


class UserActionUserCB(CallbackData, prefix="uactuser"):
    action: UserAction
    user_id: int
