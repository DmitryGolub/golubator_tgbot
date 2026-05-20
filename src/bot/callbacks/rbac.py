from aiogram.filters.callback_data import CallbackData


class RoleDetailCB(CallbackData, prefix="rbac_role"):
    role_id: int


class TogglePermCB(CallbackData, prefix="rbac_perm"):
    role_id: int
    perm_id: int


class EditPermsCB(CallbackData, prefix="rbac_edit_perms"):
    role_id: int


class DeleteRoleCB(CallbackData, prefix="rbac_del"):
    role_id: int


class ConfirmDeleteRoleCB(CallbackData, prefix="rbac_cdel"):
    role_id: int
