from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.keyboards.pagination import paginate_buttons
from src.models.lead_source import LeadSource
from src.services.ui_text import UiTextService


async def referral_link_keyboard() -> InlineKeyboardMarkup:
    back_text = await UiTextService.get("menu.back")
    kb = InlineKeyboardBuilder()
    kb.button(text=back_text, callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


async def channel_links_keyboard(
    links: list[LeadSource], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for link in links:
        label = link.label or link.code
        count_text = f"{label[:30]}"
        kb.button(text=count_text, callback_data=f"ch_detail:{link.id}")

    kb.adjust(1)

    nav = paginate_buttons("channel_links", page, total_pages)
    if nav:
        kb.row(*nav)

    kb.row()
    kb.button(text="➕ Создать ссылку", callback_data="ch_create")
    kb.button(text=await UiTextService.get("menu.back"), callback_data="back_to_menu")
    kb.adjust(1)

    return kb.as_markup()
