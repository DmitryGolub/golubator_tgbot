from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from src.bot.callbacks.cohort import (
    CohortTypeCB,
    CreateOptionCB,
    DeleteCohortTypeCB,
    DeleteOptionCB,
    RenameCohortTypeCB,
    RenameOptionCB,
)
from src.services.notion_client import CohortTypeInfo


def cohort_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Типы когорт", callback_data="cohort_list")
    kb.button(text="Создать тип когорты", callback_data="cohort_create_type")
    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def cohort_types_keyboard(types: list[CohortTypeInfo]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in types:
        label = f"{t.name} ({t.notion_type}) [{len(t.options)}]"
        kb.button(text=label, callback_data=CohortTypeCB(name=t.name).pack())
    kb.button(text="➕ Создать тип", callback_data="cohort_create_type")
    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def cohort_type_detail_keyboard(info: CohortTypeInfo) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # List options
    for opt in info.options:
        kb.button(text=f"  {opt}", callback_data=f"cohort_noop:{opt}")

    # Action buttons based on editability
    if info.editable:
        kb.button(
            text="➕ Добавить опцию",
            callback_data=CreateOptionCB(type_name=info.name).pack(),
        )
        if info.options:
            kb.button(
                text="✏️ Переименовать опцию",
                callback_data=f"cohort_rename_opt_list:{info.name}",
            )
            kb.button(
                text="🗑 Удалить опцию",
                callback_data=f"cohort_delete_opt_list:{info.name}",
            )

    if info.type_editable:
        kb.button(
            text="✏️ Переименовать тип",
            callback_data=RenameCohortTypeCB(name=info.name).pack(),
        )
        kb.button(
            text="🗑 Удалить тип",
            callback_data=DeleteCohortTypeCB(name=info.name).pack(),
        )

    kb.button(text="⬅️ Назад к типам", callback_data="cohort_list")
    kb.adjust(1)
    return kb.as_markup()


def cohort_options_select_keyboard(
    type_name: str, options: list[str], action: str
) -> InlineKeyboardMarkup:
    """Show options for selection (for rename or delete)."""
    kb = InlineKeyboardBuilder()
    for opt in options:
        if action == "delete":
            cb = DeleteOptionCB(type_name=type_name, option_name=opt).pack()
        else:  # rename
            cb = RenameOptionCB(type_name=type_name, option_name=opt).pack()
        kb.button(text=opt, callback_data=cb)
    kb.button(
        text="⬅️ Назад",
        callback_data=CohortTypeCB(name=type_name).pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def cohort_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="cohort_cancel_fsm")
    kb.adjust(1)
    return kb.as_markup()


def cohort_confirm_delete_keyboard(type_name: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Да, удалить",
        callback_data=f"cohort_confirm_del_type:{type_name}",
    )
    kb.button(text="❌ Отмена", callback_data="cohort_list")
    kb.adjust(2)
    return kb.as_markup()
