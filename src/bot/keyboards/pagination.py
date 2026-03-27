from collections.abc import Sequence
from typing import TypeVar

from aiogram.types import InlineKeyboardButton

from src.bot.callbacks.pagination import PageNavCB

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
    menu: str, current_page: int, total_pages: int
) -> list[InlineKeyboardButton]:
    if total_pages <= 1:
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
            text=f"{current_page + 1}/{total_pages}", callback_data="noop"
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
