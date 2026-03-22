from aiogram.filters.callback_data import CallbackData


class TagActionCB(CallbackData, prefix="tag_act"):
    action: str


class TagDetailCB(CallbackData, prefix="tag_detail"):
    tag_id: int


class TagAssignUserCB(CallbackData, prefix="tag_asgn_u"):
    user_id: int


class TagAssignTagCB(CallbackData, prefix="tag_asgn_t"):
    user_id: int
    tag_id: int


class TagUnassignCB(CallbackData, prefix="tag_unasgn"):
    user_id: int
    tag_id: int


class TagUnassignUserCB(CallbackData, prefix="tag_unasgn_u"):
    user_id: int


class TagDeleteCB(CallbackData, prefix="tag_del"):
    tag_id: int
