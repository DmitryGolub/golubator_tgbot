from aiogram.filters.callback_data import CallbackData


class CohortTypeCB(CallbackData, prefix="ctype"):
    """Select a cohort type by index in FSM-stored map."""

    idx: int


class CreateCohortTypeCB(CallbackData, prefix="ctype_new"):
    """Start creating a new cohort type."""

    pass


class DeleteCohortTypeCB(CallbackData, prefix="ctype_del"):
    """Delete a cohort type by index."""

    idx: int


class RenameCohortTypeCB(CallbackData, prefix="ctype_ren"):
    """Rename a cohort type by index."""

    idx: int


class CreateOptionCB(CallbackData, prefix="copt_new"):
    """Start creating an option within a cohort type by index."""

    idx: int


class DeleteOptionCB(CallbackData, prefix="copt_del"):
    """Delete an option from a cohort type by index."""

    idx: int


class RenameOptionCB(CallbackData, prefix="copt_ren"):
    """Rename an option by index."""

    idx: int


class ConfirmDeleteTypeCB(CallbackData, prefix="ctype_cdel"):
    """Confirm deletion of a cohort type by index."""

    idx: int


class OptionListCB(CallbackData, prefix="copt_ls"):
    """Show options list for rename or delete action."""

    idx: int
    action: str  # "rename" or "delete"
