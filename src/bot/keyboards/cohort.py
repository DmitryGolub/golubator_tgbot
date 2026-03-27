from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.cohort import (
    CohortTypeCB,
    ConfirmDeleteTypeCB,
    CreateOptionCB,
    DeleteCohortTypeCB,
    DeleteOptionCB,
    OptionListCB,
    RenameCohortTypeCB,
    RenameOptionCB,
)
from src.bot.keyboards.pagination import (
    DEFAULT_PAGE_SIZE,
    get_page_slice,
    paginate_buttons,
)
from src.services.notion_client import CohortTypeInfo


def cohort_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Типы когорт", callback_data="cohort_list")
    kb.button(text="Создать тип когорты", callback_data="cohort_create_type")
    kb.button(text="⬅️ Назад к меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def cohort_types_keyboard(
    types: list[CohortTypeInfo],
    page: int = 0,
) -> tuple[InlineKeyboardMarkup, dict[int, str]]:
    """Returns (keyboard, {idx: type_name}) mapping for FSM storage."""
    # Mapping uses global indices so FSM lookup works across pages
    mapping: dict[int, str] = {}
    for i, t in enumerate(types):
        mapping[i] = t.name

    page_items, total_pages = get_page_slice(types, page)
    kb = InlineKeyboardBuilder()

    nav = paginate_buttons("cohorts", page, total_pages)
    if nav:
        kb.row(*nav)

    for i, t in enumerate(page_items):
        global_idx = page * DEFAULT_PAGE_SIZE + i
        label = f"{t.name} ({t.notion_type}) [{len(t.options)}]"
        kb.row(
            InlineKeyboardButton(
                text=label, callback_data=CohortTypeCB(idx=global_idx).pack()
            )
        )

    kb.row(
        InlineKeyboardButton(text="➕ Создать тип", callback_data="cohort_create_type")
    )
    kb.row(InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="back_to_menu"))
    return kb.as_markup(), mapping


def cohort_type_detail_keyboard(
    info: CohortTypeInfo, type_idx: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # List options (non-interactive display)
    for opt in info.options:
        kb.button(text=f"  {opt}", callback_data=f"cohort_noop:{type_idx}")

    # Action buttons based on editability
    if info.editable:
        kb.button(
            text="➕ Добавить опцию",
            callback_data=CreateOptionCB(idx=type_idx),
        )
        if info.options:
            kb.button(
                text="✏️ Переименовать опцию",
                callback_data=OptionListCB(idx=type_idx, action="rename"),
            )
            kb.button(
                text="🗑 Удалить опцию",
                callback_data=OptionListCB(idx=type_idx, action="delete"),
            )

    if info.type_editable:
        kb.button(
            text="✏️ Переименовать тип",
            callback_data=RenameCohortTypeCB(idx=type_idx),
        )
        kb.button(
            text="🗑 Удалить тип",
            callback_data=DeleteCohortTypeCB(idx=type_idx),
        )

    kb.button(text="⬅️ Назад к типам", callback_data="cohort_list")
    kb.adjust(1)
    return kb.as_markup()


def cohort_options_select_keyboard(
    options: list[str], action: str
) -> tuple[InlineKeyboardMarkup, dict[int, str]]:
    """Returns (keyboard, {idx: option_name}) mapping for FSM storage."""
    kb = InlineKeyboardBuilder()
    mapping: dict[int, str] = {}
    for i, opt in enumerate(options):
        mapping[i] = opt
        if action == "delete":
            cb = DeleteOptionCB(idx=i)
        else:
            cb = RenameOptionCB(idx=i)
        kb.button(text=opt, callback_data=cb)
    kb.button(text="⬅️ Назад", callback_data="cohort_list")
    kb.adjust(1)
    return kb.as_markup(), mapping


def cohort_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="cohort_cancel_fsm")
    kb.adjust(1)
    return kb.as_markup()


def cohort_confirm_delete_keyboard(type_idx: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Да, удалить",
        callback_data=ConfirmDeleteTypeCB(idx=type_idx),
    )
    kb.button(text="❌ Отмена", callback_data="cohort_list")
    kb.adjust(2)
    return kb.as_markup()
