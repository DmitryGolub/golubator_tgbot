from collections.abc import Sequence
from typing import TypeVar

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.pagination import (
    PageJumpCB,
    PageNavCB,
    PageSearchCB,
    PageSearchResetCB,
)

DEFAULT_PAGE_SIZE = 6

T = TypeVar("T")


def get_page_slice(
    items: Sequence[T], page: int, page_size: int = DEFAULT_PAGE_SIZE
) -> tuple[Sequence[T], int]:
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start : start + page_size], total_pages


def paginate_buttons(
    menu: str,
    current_page: int,
    total_pages: int,
    search_query: str | None = None,
) -> list[InlineKeyboardButton]:
    if total_pages <= 1 and not search_query:
        return []
    buttons: list[InlineKeyboardButton] = []
    if current_page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="←",
                callback_data=PageNavCB(menu=menu, page=current_page - 1).pack(),
            )
        )
    else:
        buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    buttons.append(
        InlineKeyboardButton(
            text=f"{current_page + 1}/{total_pages}",
            callback_data=PageJumpCB(menu=menu).pack(),
        )
    )
    if search_query:
        label = f"✕ {search_query[:10]}"
        buttons.append(
            InlineKeyboardButton(
                text=label,
                callback_data=PageSearchResetCB(menu=menu).pack(),
            )
        )
    else:
        buttons.append(
            InlineKeyboardButton(
                text="🔍",
                callback_data=PageSearchCB(menu=menu).pack(),
            )
        )
    if current_page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                text="→",
                callback_data=PageNavCB(menu=menu, page=current_page + 1).pack(),
            )
        )
    else:
        buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    return buttons


def build_paginated_keyboard(
    menu: str,
    page: int,
    total_pages: int,
    item_buttons: list[InlineKeyboardButton],
    columns: int = 1,
    search_query: str | None = None,
    back_button: InlineKeyboardButton | None = None,
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    nav = paginate_buttons(menu, page, total_pages, search_query)
    if nav:
        kb.row(*nav)

    items_kb = InlineKeyboardBuilder()
    for btn in item_buttons:
        items_kb.add(btn)
    items_kb.adjust(columns)
    kb.attach(items_kb)

    if extra_rows:
        for row in extra_rows:
            kb.row(*row)

    if back_button:
        kb.row(back_button)

    return kb.as_markup()
