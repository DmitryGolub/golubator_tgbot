from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.keyboards.pagination import build_paginated_keyboard
from src.models.lead_source import LeadSource
from src.services.ui_text import UiTextService


async def referral_link_keyboard() -> InlineKeyboardMarkup:
    back_text = await UiTextService.get("menu.back")
    kb = InlineKeyboardBuilder()
    kb.button(text=back_text, callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


async def channel_links_keyboard(
    links: list[LeadSource],
    page: int,
    total_pages: int,
    search_query: str | None = None,
) -> InlineKeyboardMarkup:
    item_buttons = [
        InlineKeyboardButton(
            text=f"{(link.label or link.code)[:30]}",
            callback_data=f"ch_detail:{link.id}",
        )
        for link in links
    ]
    back_text = await UiTextService.get("menu.back")
    return build_paginated_keyboard(
        menu="channel_links",
        page=page,
        total_pages=total_pages,
        item_buttons=item_buttons,
        columns=1,
        search_query=search_query,
        extra_rows=[
            [InlineKeyboardButton(text="➕ Создать ссылку", callback_data="ch_create")],
        ],
        back_button=InlineKeyboardButton(text=back_text, callback_data="back_to_menu"),
    )
