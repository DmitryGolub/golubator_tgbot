import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks.pagination import PageNavCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.lead_source import channel_links_keyboard, referral_link_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.utils import safe_edit_text
from src.dao.lead_source import LeadSourceDAO
from src.services.lead_source import LeadSourceService
from src.services.ui_text import UiTextService

logger = logging.getLogger(__name__)

router = Router(name="lead_source")


class ChannelLinkFSM(StatesGroup):
    entering_label = State()


# ── Referral link ──


@router.callback_query(
    PermissionFilter("view_referral_link"), F.data == "menu_referral_link"
)
async def show_my_referral_link(callback: CallbackQuery):
    await callback.answer()

    bot_user = await callback.bot.get_me()
    link, count = await LeadSourceService.get_or_create_referral_link(
        callback.from_user.id, bot_user.username
    )

    text = await UiTextService.get("lead_source.my_link", link=link, count=str(count))
    await safe_edit_text(callback, text, reply_markup=await referral_link_keyboard())


# ── Channel links list ──


@router.callback_query(
    PermissionFilter("manage_channel_links"), F.data == "menu_channel_links"
)
async def show_channel_links_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await _show_channel_links_page(callback, page=0)


@router.callback_query(
    PermissionFilter("manage_channel_links"),
    PageNavCB.filter(F.menu == "channel_links"),
)
async def channel_links_page_nav(callback: CallbackQuery, callback_data: PageNavCB):
    await callback.answer()
    await _show_channel_links_page(callback, page=callback_data.page)


async def _show_channel_links_page(callback: CallbackQuery, page: int):
    links, total_pages = await LeadSourceDAO.get_channel_links(page=page)
    title = await UiTextService.get("lead_source.channel_list_title")

    if not links and page == 0:
        text = f"{title}\n\nСписок пуст."
    else:
        lines = [title, ""]
        for link in links:
            label = link.label or "—"
            count = await LeadSourceDAO.count_referrals(link.id)
            lines.append(
                f"• <b>{label}</b> — переходов: {count}\n  <code>{link.code}</code>"
            )
        text = "\n".join(lines)

    await safe_edit_text(
        callback,
        text,
        reply_markup=await channel_links_keyboard(links, page, total_pages),
    )


# ── Channel link detail ──


@router.callback_query(
    PermissionFilter("manage_channel_links"), F.data.startswith("ch_detail:")
)
async def show_channel_link_detail(callback: CallbackQuery):
    await callback.answer()
    source_id = int(callback.data.split(":")[1])
    source = await LeadSourceDAO.find_one_or_none(id=source_id)
    if not source:
        await safe_edit_text(
            callback, "Ссылка не найдена.", reply_markup=await back_to_menu_keyboard()
        )
        return

    bot_user = await callback.bot.get_me()
    link = f"https://t.me/{bot_user.username}?start={source.code}"
    count = await LeadSourceDAO.count_referrals(source.id)

    text = (
        f"📢 <b>Канальная ссылка</b>\n\n"
        f"Описание: {source.label or '—'}\n"
        f"Код: <code>{source.code}</code>\n"
        f"Ссылка: <code>{link}</code>\n"
        f"Переходов: <b>{count}</b>"
    )
    await safe_edit_text(callback, text, reply_markup=await back_to_menu_keyboard())


# ── Create channel link FSM ──


@router.callback_query(PermissionFilter("manage_channel_links"), F.data == "ch_create")
async def start_create_channel_link(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    text = await UiTextService.get("lead_source.enter_label")
    await safe_edit_text(callback, text, reply_markup=await back_to_menu_keyboard())
    await state.set_state(ChannelLinkFSM.entering_label)


@router.message(ChannelLinkFSM.entering_label)
async def process_channel_label(message: Message, state: FSMContext):
    label = message.text.strip()
    if not label:
        await message.answer("Описание не может быть пустым. Попробуйте ещё раз:")
        return

    bot_user = await message.bot.get_me()
    link = await LeadSourceService.create_channel_link(
        admin_id=message.from_user.id,
        label=label,
        bot_username=bot_user.username,
    )

    text = await UiTextService.get(
        "lead_source.channel_created", link=link, label=label
    )
    await message.answer(text, reply_markup=await back_to_menu_keyboard())
    await state.clear()
