import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.pagination import PageJumpCB, PageSearchCB, PageSearchResetCB
from src.bot.utils import safe_edit_text

logger = logging.getLogger(__name__)

router = Router(name="pagination-input")

CANCEL_PAGINATION_CB = "pagination_cancel_input"


class PaginationInputFilter(BaseFilter):
    async def __call__(self, message: Message, state: FSMContext) -> bool:
        if not message.text:
            return False
        data = await state.get_data()
        return "_pagination_ctx" in data


def _cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data=CANCEL_PAGINATION_CB))
    return kb.as_markup()


# ── PageJump: user clicks "X/Y" button ────────────────────────────────────


@router.callback_query(PageJumpCB.filter())
async def on_page_jump(
    callback: CallbackQuery, callback_data: PageJumpCB, state: FSMContext
):
    await callback.answer()
    menu = callback_data.menu

    # Parse total_pages from the button text "X/Y"
    total_pages = 1
    if callback.message and isinstance(callback.message, Message):
        markup = callback.message.reply_markup
        if markup:
            for row in markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data and btn.callback_data == callback.data:
                        parts = (btn.text or "").split("/")
                        if len(parts) == 2 and parts[1].isdigit():
                            total_pages = int(parts[1])
                        break

    msg = callback.message
    if not isinstance(msg, Message):
        return

    prompt = await msg.answer(
        f"Введите номер страницы (1–{total_pages}):",
        reply_markup=_cancel_keyboard(),
    )

    await state.update_data(
        _pagination_ctx={
            "action": "page_jump",
            "menu": menu,
            "message_id": msg.message_id,
            "prompt_id": prompt.message_id,
            "total_pages": total_pages,
        }
    )


# ── PageSearch: user clicks 🔍 button ─────────────────────────────────────


@router.callback_query(PageSearchCB.filter())
async def on_page_search(
    callback: CallbackQuery, callback_data: PageSearchCB, state: FSMContext
):
    await callback.answer()
    menu = callback_data.menu

    msg = callback.message
    if not isinstance(msg, Message):
        return

    prompt = await msg.answer(
        "Введите поисковый запрос:",
        reply_markup=_cancel_keyboard(),
    )

    await state.update_data(
        _pagination_ctx={
            "action": "search",
            "menu": menu,
            "message_id": msg.message_id,
            "prompt_id": prompt.message_id,
        }
    )


# ── PageSearchReset: user clicks "✕ query" button ─────────────────────────


@router.callback_query(PageSearchResetCB.filter())
async def on_page_search_reset(
    callback: CallbackQuery, callback_data: PageSearchResetCB, state: FSMContext
):
    await callback.answer()
    menu = callback_data.menu

    data = await state.get_data()
    search_map = data.get("_pagination_search", {})
    search_map.pop(menu, None)
    await state.update_data(_pagination_search=search_map)

    await _refresh_menu(callback, menu, 0, state)


# ── Cancel input prompt ───────────────────────────────────────────────────


@router.callback_query(F.data == CANCEL_PAGINATION_CB)
async def on_cancel_pagination_input(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await state.update_data(_pagination_ctx=None)

    if callback.message and isinstance(callback.message, Message):
        with suppress(TelegramBadRequest):
            await callback.message.delete()


# ── Text input handler (page_jump or search) ──────────────────────────────


@router.message(PaginationInputFilter())
async def on_pagination_text_input(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ctx = data.get("_pagination_ctx")
    if not ctx:
        return

    action = ctx["action"]
    menu = ctx["menu"]
    original_msg_id = ctx["message_id"]
    prompt_id = ctx.get("prompt_id")
    text = (message.text or "").strip()

    # Clean up: delete user's message and prompt
    with suppress(TelegramBadRequest):
        await message.delete()
    if prompt_id:
        with suppress(TelegramBadRequest):
            await bot.delete_message(message.chat.id, prompt_id)

    if action == "page_jump":
        total_pages = ctx.get("total_pages", 1)
        if not text.isdigit() or not (1 <= int(text) <= total_pages):
            error_prompt = await message.answer(
                f"Введите число от 1 до {total_pages}:",
                reply_markup=_cancel_keyboard(),
            )
            ctx["prompt_id"] = error_prompt.message_id
            await state.update_data(_pagination_ctx=ctx)
            return

        page = int(text) - 1
        await state.update_data(_pagination_ctx=None)
        await _refresh_menu_by_msg_id(
            bot, message.chat.id, original_msg_id, menu, page, state
        )

    elif action == "search":
        if not text:
            error_prompt = await message.answer(
                "Запрос не может быть пустым. Введите поисковый запрос:",
                reply_markup=_cancel_keyboard(),
            )
            ctx["prompt_id"] = error_prompt.message_id
            await state.update_data(_pagination_ctx=ctx)
            return

        search_map = data.get("_pagination_search", {})
        search_map[menu] = text
        await state.update_data(_pagination_search=search_map, _pagination_ctx=None)
        await _refresh_menu_by_msg_id(
            bot, message.chat.id, original_msg_id, menu, 0, state
        )


# ── Refresh helpers ───────────────────────────────────────────────────────


async def _refresh_menu(
    callback: CallbackQuery, menu: str, page: int, state: FSMContext
):
    refresher = MENU_REFRESHERS.get(menu)
    if not refresher:
        logger.warning("No refresher for menu %s", menu)
        return
    await refresher(callback, page, state)


async def _refresh_menu_by_msg_id(
    bot: Bot, chat_id: int, message_id: int, menu: str, page: int, state: FSMContext
):
    refresher = MENU_REFRESHERS_BY_MSG.get(menu)
    if not refresher:
        logger.warning("No msg refresher for menu %s", menu)
        return
    await refresher(bot, chat_id, message_id, page, state)


# ── Per-menu refresh functions ────────────────────────────────────────────


async def _refresh_users(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.user import users_keyboard
    from src.dao.user import UserDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("users")
    users_filter = data.get("users_filter", "all")
    if users_filter == "students":
        users = await UserDAO.get_all(role_name="student", include_placeholders=True)
    else:
        users = await UserDAO.get_all(include_placeholders=True)
    await safe_edit_text(
        callback,
        callback.message.text or "Выберите пользователя для редактирования:",
        reply_markup=users_keyboard(users, page=page, search_query=sq),
    )


async def _refresh_users_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    from src.bot.keyboards.user import users_keyboard
    from src.dao.user import UserDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("users")
    users_filter = data.get("users_filter", "all")
    if users_filter == "students":
        users = await UserDAO.get_all(role_name="student", include_placeholders=True)
    else:
        users = await UserDAO.get_all(include_placeholders=True)
    with suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(
            chat_id,
            message_id,
            reply_markup=users_keyboard(users, page=page, search_query=sq),
        )


async def _refresh_user_list(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.handlers.user.list import _build_user_list_page

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("user_list")
    text, markup = await _build_user_list_page(page=page, search_query=sq)
    await safe_edit_text(callback, text, reply_markup=markup)


async def _refresh_user_list_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    from src.bot.handlers.user.list import _build_user_list_page

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("user_list")
    text, markup = await _build_user_list_page(page=page, search_query=sq)
    with suppress(TelegramBadRequest):
        await bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)


async def _refresh_mentors(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.user import mentors_keyboard
    from src.dao.user import UserDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("mentors")
    mentors = await UserDAO.get_all_with_permission("manage_meetings")
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=mentors_keyboard(mentors, page=page, search_query=sq),
        )


async def _refresh_mentors_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    from src.bot.keyboards.user import mentors_keyboard
    from src.dao.user import UserDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("mentors")
    mentors = await UserDAO.get_all_with_permission("manage_meetings")
    with suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(
            chat_id,
            message_id,
            reply_markup=mentors_keyboard(mentors, page=page, search_query=sq),
        )


async def _refresh_mentees(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.user import mentees_keyboard
    from src.dao.mentee import MenteeDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("mentees")
    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=mentees_keyboard(mentees, page=page, search_query=sq),
        )


async def _refresh_mentees_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    logger.warning("mentees msg refresh not supported without user context")


async def _refresh_participants(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.meeting import meeting_participants_multiselect_keyboard
    from src.dao.mentee import MenteeDAO
    from src.dao.user import UserDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("participants")
    selected = data.get("selected_participant_ids", [])
    showing_all = data.get("showing_all", False)
    if showing_all:
        users = await UserDAO.get_all(include_placeholders=True)
    else:
        users = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=meeting_participants_multiselect_keyboard(
                users,
                selected_ids=set(selected),
                page=page,
                show_all_button=not showing_all,
                search_query=sq,
            )
        )


async def _refresh_participants_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    # Participants refresh requires user_id context — handled via callback path
    logger.warning("participants msg refresh not supported without user context")


async def _refresh_meetings(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.meeting import mentor_meetings_keyboard
    from src.dao.meeting import MeetingDAO
    from src.dao.mentor import MentorDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("meetings")
    from src.bot.handlers.meeting import _filter_visible_meetings, _format_meetings

    meetings = await MeetingDAO.get_for_user(callback.from_user.id, hide_past=True)
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    visible = _filter_visible_meetings(
        meetings,
        callback.from_user.id,
        viewer_is_mentor=True,
        mentor_tg_ids=mentor_tg_ids,
    )
    text = _format_meetings(visible, mentor_tg_ids=mentor_tg_ids, page=page)
    await safe_edit_text(
        callback,
        text,
        reply_markup=mentor_meetings_keyboard(
            visible, page=page, viewer_id=callback.from_user.id, search_query=sq
        ),
    )


async def _refresh_meetings_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    logger.warning("meetings msg refresh not supported without user context")


async def _refresh_past_meetings(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.meeting import (
        mentor_past_meetings_keyboard,
        student_past_meetings_keyboard,
    )
    from src.dao.meeting import MeetingDAO
    from src.dao.mentor import MentorDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("past_meetings")
    from src.bot.handlers.meeting import _filter_visible_meetings, _format_meetings

    meetings = await MeetingDAO.get_for_user(callback.from_user.id, only_past=True)
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    is_mentor = callback.from_user.id in mentor_tg_ids
    visible = _filter_visible_meetings(
        meetings,
        callback.from_user.id,
        viewer_is_mentor=is_mentor,
        mentor_tg_ids=mentor_tg_ids,
    )
    text = _format_meetings(
        visible, mentor_tg_ids=mentor_tg_ids, page=page, title="Завершённые созвоны:"
    )
    if is_mentor:
        markup = mentor_past_meetings_keyboard(
            visible, page=page, viewer_id=callback.from_user.id, search_query=sq
        )
    else:
        markup = student_past_meetings_keyboard(visible, page=page, search_query=sq)
    await safe_edit_text(callback, text, reply_markup=markup)


async def _refresh_past_meetings_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    logger.warning("past_meetings msg refresh not supported without user context")


async def _refresh_meeting_types(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.meeting import meeting_type_keyboard

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("meeting_types")
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=meeting_type_keyboard(page=page, search_query=sq)
        )


async def _refresh_meeting_types_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    from src.bot.keyboards.meeting import meeting_type_keyboard

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("meeting_types")
    with suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(
            chat_id,
            message_id,
            reply_markup=meeting_type_keyboard(page=page, search_query=sq),
        )


async def _refresh_cohorts(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.cohort import cohort_types_keyboard
    from src.dao.cohort import CohortDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("cohorts")
    types_with_counts = await CohortDAO.get_types_with_value_counts()
    markup, types_map = cohort_types_keyboard(
        types_with_counts, page=page, search_query=sq
    )
    await state.update_data(cohort_types_map=types_map)
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=markup)


async def _refresh_cohorts_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    from src.bot.keyboards.cohort import cohort_types_keyboard
    from src.dao.cohort import CohortDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("cohorts")
    types_with_counts = await CohortDAO.get_types_with_value_counts()
    markup, types_map = cohort_types_keyboard(
        types_with_counts, page=page, search_query=sq
    )
    await state.update_data(cohort_types_map=types_map)
    with suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(chat_id, message_id, reply_markup=markup)


async def _refresh_mstats(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.mentor_stats import mentor_select_keyboard
    from src.dao.mentor import MentorDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("mstats")
    all_mentors = await MentorDAO.get_all_with_users()
    mentors = [m for m in all_mentors if m.telegram_id is not None]
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=mentor_select_keyboard(mentors, page=page, search_query=sq)
        )


async def _refresh_mstats_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    from src.bot.keyboards.mentor_stats import mentor_select_keyboard
    from src.dao.mentor import MentorDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("mstats")
    all_mentors = await MentorDAO.get_all_with_users()
    mentors = [m for m in all_mentors if m.telegram_id is not None]
    with suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(
            chat_id,
            message_id,
            reply_markup=mentor_select_keyboard(mentors, page=page, search_query=sq),
        )


async def _refresh_channel_links(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.handlers.lead_source import _show_channel_links_page

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("channel_links")
    await _show_channel_links_page(callback, page=page, search_query=sq)


async def _refresh_channel_links_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    from src.bot.keyboards.lead_source import channel_links_keyboard
    from src.dao.lead_source import LeadSourceDAO
    from src.services.ui_text import UiTextService

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("channel_links")
    links, total_pages = await LeadSourceDAO.get_channel_links(page=page, search=sq)
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

    with suppress(TelegramBadRequest):
        await bot.edit_message_text(
            text,
            chat_id,
            message_id,
            reply_markup=await channel_links_keyboard(
                links, page, total_pages, search_query=sq
            ),
        )


async def _refresh_students(callback: CallbackQuery, page: int, state: FSMContext):
    from src.bot.keyboards.meeting import meeting_students_keyboard
    from src.dao.mentee import MenteeDAO

    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("students")
    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=meeting_students_keyboard(mentees, page=page, search_query=sq)
        )


async def _refresh_students_msg(
    bot: Bot, chat_id: int, message_id: int, page: int, state: FSMContext
):
    logger.warning("students msg refresh not supported without user context")


# ── Dispatch tables ───────────────────────────────────────────────────────

MENU_REFRESHERS: dict = {
    "users": _refresh_users,
    "user_list": _refresh_user_list,
    "mentors": _refresh_mentors,
    "mentees": _refresh_mentees,
    "participants": _refresh_participants,
    "meetings": _refresh_meetings,
    "past_meetings": _refresh_past_meetings,
    "meeting_types": _refresh_meeting_types,
    "cohorts": _refresh_cohorts,
    "mstats": _refresh_mstats,
    "channel_links": _refresh_channel_links,
    "students": _refresh_students,
}

MENU_REFRESHERS_BY_MSG: dict = {
    "users": _refresh_users_msg,
    "user_list": _refresh_user_list_msg,
    "mentors": _refresh_mentors_msg,
    "mentees": _refresh_mentees_msg,
    "participants": _refresh_participants_msg,
    "meetings": _refresh_meetings_msg,
    "past_meetings": _refresh_past_meetings_msg,
    "meeting_types": _refresh_meeting_types_msg,
    "cohorts": _refresh_cohorts_msg,
    "mstats": _refresh_mstats_msg,
    "channel_links": _refresh_channel_links_msg,
    "students": _refresh_students_msg,
}
