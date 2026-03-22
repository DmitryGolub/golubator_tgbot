from aiogram.filters.callback_data import CallbackData


class CohortTypeCB(CallbackData, prefix="ctype"):
    """Select a cohort type (Notion property name)."""
    name: str


class CreateCohortTypeCB(CallbackData, prefix="ctype_new"):
    """Start creating a new cohort type."""
    pass


class DeleteCohortTypeCB(CallbackData, prefix="ctype_del"):
    """Delete a cohort type."""
    name: str


class RenameCohortTypeCB(CallbackData, prefix="ctype_ren"):
    """Rename a cohort type."""
    name: str


class CreateOptionCB(CallbackData, prefix="copt_new"):
    """Start creating an option within a cohort type."""
    type_name: str


class DeleteOptionCB(CallbackData, prefix="copt_del"):
    """Delete an option from a cohort type."""
    type_name: str
    option_name: str


class RenameOptionCB(CallbackData, prefix="copt_ren"):
    """Rename an option."""
    type_name: str
    option_name: str
