import asyncio
from dataclasses import dataclass

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from datetime import datetime, date, timezone

from src.utils.tz import MSK

from src.bot.callbacks.meeting import (
    ChooseMeetingTypeCB,
    ConfirmMeetingCB,
    ConfirmParticipantSelectionCB,
    DeclineMeetingCB,
    DeleteMeetingCB,
    EditMeetingCB,
    EditMeetingFieldCB,
    ProposeNewTimeCB,
    ShowAllUsersCB,
    StartMeetingCallCB,
    ChooseMeetingDateCB,
    NavigateMeetingMonthCB,
    ChooseMeetingTimeCB,
    ToggleMeetingParticipantCB,
)
from src.bot.callbacks.pagination import PageNavCB
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.meeting import (
    mentor_meetings_keyboard,
    mentor_past_meetings_keyboard,
    student_meetings_keyboard,
    student_past_meetings_keyboard,
    meeting_cancel_keyboard,
    meeting_link_cancel_keyboard,
    meeting_participants_multiselect_keyboard,
    meeting_type_keyboard,
    meeting_calendar_keyboard,
    meeting_time_keyboard,
    pending_meeting_keyboard,
    edit_meeting_fields_keyboard,
)
from src.bot.keyboards.menu import menu_keyboard
from src.bot.keyboards.pagination import DEFAULT_PAGE_SIZE
from src.bot.states.meeting import ApproveMeetingFSM, CreateMeetingFSM, EditMeetingFSM
from src.dao.meeting import MeetingDAO
from src.dao.mentor import MentorDAO
from src.dao.user import UserDAO
from src.dao.mentee import MenteeDAO
from src.models.meeting import CallStatus, ProposalStatus
from src.services.auth import AuthService
from src.services.meeting.proposal_text import format_proposal_text
from src.bot.handlers.pagination_input import clear_pagination_ctx
from src.bot.keyboards.utils import format_username_display
from src.bot.labels import MEETING_FIELD_LABELS
from src.bot.utils import safe_edit_text
from src.core.config import settings
from src.utils.escape import e
import logging
from src.services.call_flow import (
    ActiveCallAlreadyExistsError,
    CallAlreadyExistsError,
    CallFlowService,
    MeetingAlreadyCompletedError,
    MeetingNotFoundError,
    MentorNotInMeetingError,
    NoOtherParticipantsError,
)

logger = logging.getLogger(__name__)
MOSCOW_TZ = MSK


def _trigger_caldav_sync(meeting_id: int) -> None:
    """Dispatch a CalDAV push for a meeting (no-op when feature is off)."""
    if not settings.CALDAV_ENABLED:
        return
    try:
        from src.tasks.caldav import sync_meeting

        sync_meeting.delay(meeting_id)
    except Exception:
        logger.exception(
            "Failed to dispatch caldav.sync_meeting",
            extra={"meeting_id": meeting_id},
        )


async def _trigger_caldav_delete(meeting_id: int) -> None:
    """Snapshot and dispatch a CalDAV delete for a meeting."""
    if not settings.CALDAV_ENABLED:
        return
    try:
        from src.dao.caldav_event_link import CalDAVEventLinkDAO
        from src.tasks.caldav import delete_events_for_meeting

        snapshot = await CalDAVEventLinkDAO.find_by_meeting(meeting_id)
        if not snapshot:
            return
        payload = [
            [s.link_id, s.account_id, s.event_uid, s.event_href, s.etag]
            for s in snapshot
        ]
        delete_events_for_meeting.delay(meeting_id, payload)
    except Exception:
        logger.exception(
            "Failed to dispatch caldav.delete_events_for_meeting",
            extra={"meeting_id": meeting_id},
        )


router = Router(name="meetings")
router.message.filter(
    PermissionFilter(["manage_meetings", "view_own_meetings", "propose_meetings"])
)
router.callback_query.filter(
    PermissionFilter(["manage_meetings", "view_own_meetings", "propose_meetings"])
)


async def _menu_kb(user_id: int):
    perms = await AuthService.get_user_permissions(user_id)
    return await menu_keyboard(perms)


def _resolve_participants(meeting, mentor_tg_ids: set[int]):
    """Return (creator, list[others]) for a meeting."""
    creator = next(
        (
            p
            for p in meeting.participants
            if p.telegram_id == meeting.mentor_telegram_id
        ),
        None,
    )
    if not creator:
        creator = next(
            (p for p in meeting.participants if p.telegram_id in mentor_tg_ids),
            None,
        )
    others = [
        p
        for p in meeting.participants
        if not creator or p.telegram_id != creator.telegram_id
    ]
    return creator, others


def _filter_visible_meetings(
    meetings, viewer_id: int, viewer_is_mentor: bool, mentor_tg_ids: set[int]
) -> list:
    result = []
    for meeting in meetings:
        participant_ids = {p.telegram_id for p in meeting.participants}
        if viewer_id in participant_ids:
            result.append(meeting)
            continue
        # Backward compat: check legacy fields
        if viewer_is_mentor and meeting.mentor_telegram_id == viewer_id:
            result.append(meeting)
        elif not viewer_is_mentor and meeting.student_telegram_id == viewer_id:
            result.append(meeting)
    return result


def _format_meetings(
    meetings,
    mentor_tg_ids: set[int],
    page: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
    title: str = "Мои созвоны:",
) -> str:
    if not meetings:
        return f"<b>{title}</b>\n\nСписок созвонов пуст."

    start = page * page_size
    page_meetings = meetings[start : start + page_size]

    lines = [f"<b>{title}</b>", ""]
    for local_idx, meeting in enumerate(page_meetings):
        display_idx = start + local_idx + 1

        creator, others = _resolve_participants(meeting, mentor_tg_ids)

        creator_text = (
            f"Организатор: <b>{e(creator.name)}</b>"
            + format_username_display(creator.username)
            if creator
            else "Организатор: —"
        )
        if others:
            names = [
                f"<b>{e(p.name)}</b>" + format_username_display(p.username)
                for p in others
            ]
            others_text = f"Участники: {', '.join(names)}"
        elif meeting.mentee_telegram_tag:
            others_text = f"Участники: {e(meeting.mentee_telegram_tag)}"
        else:
            others_text = "Участники: —"
        desc = e(meeting.description) if meeting.description else "—"
        link = e(meeting.meeting_link) if meeting.meeting_link else "—"
        if meeting.scheduled_at:
            try:
                date_str = meeting.scheduled_at.astimezone(MOSCOW_TZ).strftime(
                    "%d.%m.%Y %H:%M MSK"
                )
            except Exception:
                date_str = meeting.scheduled_at.isoformat()
        else:
            date_str = "—"

        status_tag = ""
        if meeting.proposal_status == ProposalStatus.pending_confirmation:
            status_tag = " ⏳ожидает подтверждения"

        lines.append(
            f"🗓 Созвон #{display_idx}{status_tag}\n"
            f"{creator_text}\n"
            f"{others_text}\n"
            f"Когда: {date_str}\n"
            f"Описание: {desc}\n"
            f"Ссылка: {link}\n"
        )
    return "\n".join(lines)


@dataclass
class MeetingsView:
    text: str
    visible: list
    mentor_tg_ids: set[int]


async def prepare_meetings_view(
    user_id: int,
    *,
    hide_past: bool = False,
    only_past: bool = False,
    viewer_is_mentor: bool = True,
    page: int = 0,
    title: str = "Мои созвоны:",
    text_prefix: str = "",
) -> MeetingsView:
    meetings = await MeetingDAO.get_for_user(
        user_id, hide_past=hide_past, only_past=only_past
    )
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    visible = _filter_visible_meetings(
        meetings,
        user_id,
        viewer_is_mentor=viewer_is_mentor,
        mentor_tg_ids=mentor_tg_ids,
    )
    text = text_prefix + _format_meetings(
        visible, mentor_tg_ids=mentor_tg_ids, page=page, title=title
    )
    return MeetingsView(text=text, visible=visible, mentor_tg_ids=mentor_tg_ids)


_format_proposal_text = format_proposal_text


@router.callback_query(
    PermissionFilter("manage_meetings"),
    F.data.in_({"mentor_meetings_list", "mentor_meetings_menu"}),
)
async def cb_mentor_meetings(callback: CallbackQuery):
    await callback.answer()
    view = await prepare_meetings_view(callback.from_user.id, hide_past=True)
    await safe_edit_text(
        callback,
        view.text,
        reply_markup=mentor_meetings_keyboard(
            view.visible, page=0, viewer_id=callback.from_user.id
        ),
    )


@router.callback_query(
    PermissionFilter("view_own_meetings"), F.data == "student_meetings"
)
async def cb_student_meetings(callback: CallbackQuery):
    await callback.answer()
    view = await prepare_meetings_view(
        callback.from_user.id, hide_past=True, viewer_is_mentor=False
    )
    mentee = await MenteeDAO.find_by_telegram_id(callback.from_user.id)
    has_mentor = bool(mentee and mentee.mentor and mentee.mentor.telegram_id)
    await safe_edit_text(
        callback,
        view.text,
        reply_markup=await student_meetings_keyboard(
            view.visible,
            page=0,
            viewer_id=callback.from_user.id,
            has_mentor=has_mentor,
        ),
    )


@router.callback_query(PermissionFilter("manage_meetings"), StartMeetingCallCB.filter())
async def cb_start_meeting_call(
    callback: CallbackQuery,
    callback_data: StartMeetingCallCB,
):
    await callback.answer()

    service = CallFlowService()

    try:
        await service.start_call(
            mentor_id=callback.from_user.id,
            meeting_id=callback_data.meeting_id,
        )
    except MeetingNotFoundError:
        text = "Созвон не найден."
    except MentorNotInMeetingError:
        text = "У вас нет доступа к этому созвону."
    except MeetingAlreadyCompletedError:
        text = "Этот созвон уже завершён."
    except NoOtherParticipantsError:
        text = "В созвоне нет других участников."
    except ActiveCallAlreadyExistsError as exc:
        if exc.meeting.id == callback_data.meeting_id:
            text = "Этот созвон уже запущен и числится активным."
        else:
            text = (
                "У вас уже есть активный созвон. "
                "Сначала завершите его через кнопку или команду /end_call."
            )
    except CallAlreadyExistsError as exc:
        if exc.meeting.call_status == CallStatus.ongoing:
            text = "Этот созвон уже запущен и числится активным."
        else:
            text = "Для этого созвона уже есть завершённая сессия."
    else:
        text = (
            f"✅ Созвон по встрече #{callback_data.meeting_id} начат.\n\n"
            "После окончания используйте кнопку «Завершить активный созвон» "
            "или команду /end_call."
        )

    view = await prepare_meetings_view(callback.from_user.id)
    await safe_edit_text(
        callback,
        text,
        reply_markup=mentor_meetings_keyboard(
            view.visible, page=0, viewer_id=callback.from_user.id
        ),
    )


@router.callback_query(PermissionFilter("manage_meetings"), F.data == "meeting_create")
async def cb_meeting_create(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    if not mentees:
        await safe_edit_text(
            callback,
            "У вас пока нет менти.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        return

    await state.update_data(selected_participant_ids=[], showing_all=False)
    await state.set_state(CreateMeetingFSM.choosing_student)
    await safe_edit_text(
        callback,
        "Выберите участников для созвона:",
        reply_markup=meeting_participants_multiselect_keyboard(
            mentees, selected_ids=set(), show_all_button=True
        ),
    )


@router.callback_query(
    PermissionFilter("propose_meetings"),
    F.data == "student_propose_meeting",
)
async def cb_student_propose_meeting(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id

    mentee = await MenteeDAO.find_by_telegram_id(user_id)
    if not mentee or not mentee.mentor or not mentee.mentor.telegram_id:
        await safe_edit_text(
            callback,
            "У вас нет ментора. Обратитесь к куратору.",
            reply_markup=await _menu_kb(user_id),
        )
        return

    mentor_tg_id = mentee.mentor.telegram_id
    username = callback.from_user.username
    default_topic = f"Созвон с @{username}" if username else "Созвон"
    await state.update_data(
        mentor_id=mentor_tg_id,
        student_id=user_id,
        event_type="Обучение",
        description=default_topic,
        is_student_proposal=True,
    )
    await state.set_state(CreateMeetingFSM.waiting_date)
    await safe_edit_text(
        callback,
        "Выберите дату для созвона с ментором:",
        reply_markup=meeting_calendar_keyboard(datetime.now(MSK).date()),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_student),
    ToggleMeetingParticipantCB.filter(),
)
async def cb_toggle_participant(
    callback: CallbackQuery,
    callback_data: ToggleMeetingParticipantCB,
    state: FSMContext,
):
    await callback.answer()
    data = await state.get_data()
    selected: list[int] = data.get("selected_participant_ids", [])
    uid = callback_data.user_id
    if uid in selected:
        selected.remove(uid)
    else:
        selected.append(uid)
    await state.update_data(selected_participant_ids=selected)

    page = callback_data.page
    sq = (data.get("_pagination_search") or {}).get("participants")
    showing_all = data.get("showing_all", False)
    if showing_all:
        users = await UserDAO.get_all()
    else:
        users = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    for attempt in range(3):
        try:
            await callback.message.edit_reply_markup(
                reply_markup=meeting_participants_multiselect_keyboard(
                    users,
                    selected_ids=set(selected),
                    page=page,
                    show_all_button=not showing_all,
                    search_query=sq,
                ),
            )
            break
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
            break
        except TelegramNetworkError:
            if attempt == 2:
                raise
            await asyncio.sleep(0.5)


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_student),
    ShowAllUsersCB.filter(),
)
async def cb_show_all_users(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    selected: list[int] = data.get("selected_participant_ids", [])
    await state.update_data(showing_all=True)

    users = await UserDAO.get_all()
    await callback.message.edit_reply_markup(
        reply_markup=meeting_participants_multiselect_keyboard(
            users, selected_ids=set(selected), show_all_button=False
        ),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_student),
    ConfirmParticipantSelectionCB.filter(),
)
async def cb_confirm_participant_selection(
    callback: CallbackQuery, state: FSMContext, bot: Bot
):
    await callback.answer()
    data = await state.get_data()
    selected: list[int] = data.get("selected_participant_ids", [])
    if not selected:
        await callback.answer("Выберите хотя бы одного участника.", show_alert=True)
        return

    await clear_pagination_ctx(state, bot, callback.message.chat.id)
    await state.update_data(participant_ids=selected)
    await state.set_state(CreateMeetingFSM.choosing_type)

    await safe_edit_text(
        callback,
        "Выберите тип встречи:",
        reply_markup=meeting_type_keyboard(),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_type),
    ChooseMeetingTypeCB.filter(),
)
async def cb_choose_meeting_type(
    callback: CallbackQuery,
    callback_data: ChooseMeetingTypeCB,
    state: FSMContext,
    bot: Bot,
):
    await callback.answer()
    await clear_pagination_ctx(state, bot, callback.message.chat.id)
    from src.bot.keyboards.meeting import MEETING_TYPES

    if callback_data.type_idx >= len(MEETING_TYPES):
        await safe_edit_text(
            callback,
            "Неверный тип встречи.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        await state.clear()
        return

    await state.update_data(event_type=MEETING_TYPES[callback_data.type_idx])
    await state.set_state(CreateMeetingFSM.waiting_description)

    await safe_edit_text(
        callback,
        "Введите описание встречи:",
        reply_markup=meeting_cancel_keyboard(),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_type),
    F.data == "meeting_skip_type",
)
async def cb_skip_meeting_type(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await clear_pagination_ctx(state, bot, callback.message.chat.id)
    await state.set_state(CreateMeetingFSM.waiting_description)

    await safe_edit_text(
        callback,
        "Введите описание встречи:",
        reply_markup=meeting_cancel_keyboard(),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_type),
    PageNavCB.filter(F.menu == "meeting_types"),
)
async def cb_meeting_types_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    data = await state.get_data()
    search_query = (data.get("_pagination_search") or {}).get("meeting_types")
    await callback.message.edit_reply_markup(
        reply_markup=meeting_type_keyboard(
            page=callback_data.page, search_query=search_query
        )
    )


@router.message(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.waiting_description),
)
async def msg_meeting_description(message: Message, state: FSMContext):
    description = message.text.strip() if message.text else ""
    await state.update_data(description=description)
    await state.set_state(CreateMeetingFSM.waiting_date)

    await message.answer(
        "Выберите дату встречи:",
        reply_markup=meeting_calendar_keyboard(datetime.now(MSK).date()),
    )


@router.callback_query(
    PermissionFilter(["manage_meetings", "propose_meetings"]),
    StateFilter(CreateMeetingFSM.waiting_date, EditMeetingFSM.editing_datetime_date),
    NavigateMeetingMonthCB.filter(),
)
async def cb_meeting_nav_month(
    callback: CallbackQuery,
    callback_data: NavigateMeetingMonthCB,
    state: FSMContext,
):
    await callback.answer()
    year = callback_data.year
    month = callback_data.month + callback_data.delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    await callback.message.edit_reply_markup(
        reply_markup=meeting_calendar_keyboard(date(year, month, 1))
    )


@router.callback_query(
    PermissionFilter(["manage_meetings", "propose_meetings"]),
    StateFilter(CreateMeetingFSM.waiting_date, EditMeetingFSM.editing_datetime_date),
    ChooseMeetingDateCB.filter(),
)
async def cb_meeting_choose_date(
    callback: CallbackQuery,
    callback_data: ChooseMeetingDateCB,
    state: FSMContext,
):
    await callback.answer()
    chosen_date = date(callback_data.year, callback_data.month, callback_data.day)
    today_msk = datetime.now(MOSCOW_TZ).date()
    if chosen_date < today_msk:
        await callback.answer(
            "Выберите сегодняшнюю или более позднюю дату.", show_alert=True
        )
        return
    await state.update_data(chosen_date=chosen_date.isoformat())

    current_state = await state.get_state()
    if current_state == EditMeetingFSM.editing_datetime_date.state:
        await state.set_state(EditMeetingFSM.editing_datetime_time)
    else:
        await state.set_state(CreateMeetingFSM.waiting_time)

    await safe_edit_text(
        callback,
        f"Дата выбрана: {chosen_date:%d.%m.%Y}\nТеперь выберите время или введите его в формате HH:MM.",
        reply_markup=meeting_time_keyboard(),
    )


def _parse_time(value: str) -> str | None:
    raw = (value or "").strip()
    if ":" in raw:
        try:
            return datetime.strptime(raw, "%H:%M").strftime("%H:%M")
        except ValueError:
            return None
    if len(raw) == 4 and raw.isdigit():
        try:
            return datetime.strptime(raw, "%H%M").strftime("%H:%M")
        except ValueError:
            return None
    return None


@router.message(
    PermissionFilter(["manage_meetings", "propose_meetings"]),
    StateFilter(CreateMeetingFSM.waiting_time, EditMeetingFSM.editing_datetime_time),
)
async def msg_meeting_time(message: Message, state: FSMContext):
    parsed = _parse_time(message.text)
    if not parsed:
        await message.answer(
            "Не удалось распознать время. Введите в формате HH:MM, например 18:00.",
            reply_markup=meeting_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    chosen_date = data.get("chosen_date")
    if not chosen_date:
        await state.clear()
        await message.answer(
            "Дата не выбрана, начните заново.",
            reply_markup=await _menu_kb(message.from_user.id),
        )
        return

    scheduled_iso = f"{chosen_date} {parsed}"
    scheduled_at_utc = _to_utc_assuming_msk(_parse_datetime(scheduled_iso))
    if scheduled_at_utc and _is_past(scheduled_at_utc):
        await message.answer(
            "Это время уже прошло. Введите время в будущем в формате HH:MM:",
            reply_markup=meeting_time_keyboard(),
        )
        return

    await state.update_data(scheduled_at=scheduled_iso)

    current_state = await state.get_state()
    if current_state == EditMeetingFSM.editing_datetime_time.state:
        if not scheduled_at_utc:
            await message.answer(
                "Не удалось сохранить дату/время.",
                reply_markup=await _menu_kb(message.from_user.id),
            )
            await state.clear()
            return
        await _save_edit_and_return(
            message.from_user.id,
            state,
            message.answer,
            message.bot,
            scheduled_at=scheduled_at_utc,
        )
    else:
        data = await state.get_data()
        if data.get("reschedule_meeting_id"):
            await _finalize_reschedule(
                message.from_user.id, state, message.answer, message.bot
            )
        elif data.get("is_student_proposal"):
            await _finalize_meeting(
                user_id=message.from_user.id,
                state=state,
                link=None,
                reply_func=message.answer,
                bot=message.bot,
            )
        else:
            await state.set_state(CreateMeetingFSM.waiting_link)
            await message.answer(
                "Введите ссылку на встречу (Telemost, Zoom, Google Meet и т.д.):",
                reply_markup=meeting_link_cancel_keyboard(),
            )


@router.callback_query(
    PermissionFilter(["manage_meetings", "propose_meetings"]),
    StateFilter(CreateMeetingFSM.waiting_time, EditMeetingFSM.editing_datetime_time),
    ChooseMeetingTimeCB.filter(),
)
async def cb_meeting_choose_time(
    callback: CallbackQuery,
    callback_data: ChooseMeetingTimeCB,
    state: FSMContext,
):
    await callback.answer()
    data = await state.get_data()
    chosen_date = data.get("chosen_date")
    if not chosen_date:
        await state.clear()
        await safe_edit_text(
            callback,
            "Дата не выбрана, начните заново.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        return

    hhmm = callback_data.t
    hh, mm = hhmm[:2], hhmm[2:]
    scheduled_iso = f"{chosen_date} {hh}:{mm}"
    scheduled_at_utc = _to_utc_assuming_msk(_parse_datetime(scheduled_iso))
    if scheduled_at_utc and _is_past(scheduled_at_utc):
        await safe_edit_text(
            callback,
            "Это время уже прошло. Выберите будущее время или введите HH:MM:",
            reply_markup=meeting_time_keyboard(),
        )
        return

    await state.update_data(scheduled_at=scheduled_iso)

    current_state = await state.get_state()
    if current_state == EditMeetingFSM.editing_datetime_time.state:
        if not scheduled_at_utc:
            await safe_edit_text(
                callback,
                "Не удалось сохранить дату/время.",
                reply_markup=await _menu_kb(callback.from_user.id),
            )
            await state.clear()
            return
        await _save_edit_and_return(
            callback.from_user.id,
            state,
            lambda text, **kw: safe_edit_text(callback, text, **kw),
            callback.bot,
            scheduled_at=scheduled_at_utc,
        )
    else:
        data = await state.get_data()
        if data.get("reschedule_meeting_id"):
            await _finalize_reschedule(
                callback.from_user.id,
                state,
                lambda text, **kw: safe_edit_text(callback, text, **kw),
                callback.bot,
            )
        elif data.get("is_student_proposal"):
            await _finalize_meeting(
                user_id=callback.from_user.id,
                state=state,
                link=None,
                reply_func=lambda text, **kw: safe_edit_text(callback, text, **kw),
                bot=callback.bot,
            )
        else:
            await state.set_state(CreateMeetingFSM.waiting_link)
            await safe_edit_text(
                callback,
                "Введите ссылку на встречу (Telemost, Zoom, Google Meet и т.д.):",
                reply_markup=meeting_link_cancel_keyboard(),
            )


def _parse_datetime(value: str) -> datetime | None:
    # Support ISO and "YYYY-MM-DD HH:MM"
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y%m%d%H%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(value)
        return dt
    except Exception:
        return None


def _to_utc_assuming_msk(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MOSCOW_TZ)
    return dt.astimezone(timezone.utc)


def _is_past(scheduled_at: datetime | None) -> bool:
    if scheduled_at is None:
        return False
    return scheduled_at <= datetime.now(timezone.utc)


async def _schedule_meeting_tasks(meeting) -> None:
    meeting_id = meeting.id
    scheduled_at = meeting.scheduled_at

    scheduled_utc = _to_utc_assuming_msk(scheduled_at)

    # Backward compat: first non-creator as student_id
    participant_ids = [p.telegram_id for p in meeting.participants]
    student_id = next(
        (pid for pid in participant_ids if pid != meeting.mentor_telegram_id), None
    )

    # Trigger system handles both created-notification and reminder
    try:
        from src.models.trigger import TriggerType
        from src.services.events.dispatcher import EventDispatcher

        await EventDispatcher.emit(
            TriggerType.meeting_created,
            {
                "meeting_id": meeting_id,
                "mentor_id": meeting.mentor_telegram_id,
                "student_id": student_id,
                "participant_ids": participant_ids,
                "scheduled_at": scheduled_utc.isoformat() if scheduled_utc else None,
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to emit meeting_created event for meeting %s: %s", meeting_id, exc
        )


async def _finalize_reschedule(user_id: int, state: FSMContext, reply_func, bot):
    data = await state.get_data()
    meeting_id = data.get("reschedule_meeting_id")
    scheduled_at_raw = data.get("scheduled_at")
    scheduled_at = (
        _to_utc_assuming_msk(_parse_datetime(scheduled_at_raw))
        if scheduled_at_raw
        else None
    )

    if not scheduled_at or not meeting_id:
        await reply_func(
            "Не удалось сохранить дату/время. Попробуйте заново.",
            reply_markup=await _menu_kb(user_id),
        )
        await state.clear()
        return

    if _is_past(scheduled_at):
        await reply_func(
            "Нельзя перенести созвон на прошедшее время. "
            "Выберите дату и время в будущем.",
            reply_markup=await _menu_kb(user_id),
        )
        await state.clear()
        return

    meeting = await MeetingDAO.propose_reschedule(
        meeting_id=meeting_id,
        new_scheduled_at=scheduled_at,
        new_link=None,
        proposer_id=user_id,
    )
    await state.clear()

    if meeting:
        _trigger_caldav_sync(meeting.id)

    if not meeting:
        await reply_func(
            "Не удалось обновить созвон. Возможно, он уже завершён.",
            reply_markup=await _menu_kb(user_id),
        )
        return

    proposer = await UserDAO.find_one_or_none(telegram_id=user_id)
    proposer_name = proposer.name if proposer else "Неизвестный участник"

    for p in meeting.participants:
        if p.telegram_id == user_id:
            continue
        try:
            await bot.send_message(
                p.telegram_id,
                _format_proposal_text(meeting, proposer_name),
                reply_markup=pending_meeting_keyboard(meeting.id),
            )
        except Exception as exc:
            logger.error(
                "Failed to send reschedule proposal to %s for meeting %s: %s",
                p.telegram_id,
                meeting.id,
                exc,
            )

    await reply_func(
        "Предложение о переносе отправлено, ожидаем подтверждения.",
        reply_markup=await _menu_kb(user_id),
    )


async def _finalize_meeting(
    user_id: int, state: FSMContext, link: str | None, reply_func, bot
):
    data = await state.get_data()

    mentor_id_from_state = data.get("mentor_id")
    if mentor_id_from_state:
        creator_id = mentor_id_from_state
    else:
        creator_id = user_id

    # Multi-select participant_ids or fallback to old student_id
    participant_ids: list[int] = data.get("participant_ids", [])
    student_id = data.get("student_id")
    if not participant_ids and student_id:
        participant_ids = [student_id]

    description = data.get("description")
    event_type = data.get("event_type")
    scheduled_at_raw = data.get("scheduled_at")
    scheduled_at = None
    if scheduled_at_raw:
        scheduled_at = _to_utc_assuming_msk(_parse_datetime(scheduled_at_raw))

    if not scheduled_at:
        await reply_func(
            "Не удалось сохранить дату/время. Попробуйте создать созвон заново.",
            reply_markup=await _menu_kb(user_id),
        )
        await state.clear()
        return

    if _is_past(scheduled_at):
        await reply_func(
            "Нельзя назначить созвон на прошедшее время. "
            "Выберите дату и время в будущем.",
            reply_markup=await _menu_kb(user_id),
        )
        await state.clear()
        return

    # Resolve participant usernames for Notion sync (comma-separated tags)
    mentee_tags: list[str] = []
    for pid in participant_ids:
        if pid == creator_id:
            continue
        user = await UserDAO.find_one_or_none(telegram_id=pid)
        if user and user.username:
            mentee_tags.append(f"@{user.username}")
        elif user and user.name:
            mentee_tags.append(user.name)
    mentee_tag = ", ".join(mentee_tags) if mentee_tags else None

    meeting = await MeetingDAO.create_with_participants(
        description=description,
        meeting_link=link,
        scheduled_at=scheduled_at,
        creator_id=creator_id,
        participant_ids=participant_ids,
        topic=description,
        event_type=event_type,
        mentee_telegram_tag=mentee_tag,
        proposal_status=ProposalStatus.pending_confirmation,
        proposed_by=user_id,
    )
    await state.clear()

    _trigger_caldav_sync(meeting.id)

    # Get proposer name for notification
    proposer = await UserDAO.find_one_or_none(telegram_id=user_id)
    proposer_name = proposer.name if proposer else "Неизвестный участник"

    # Send proposal to ALL participants except the initiator
    all_ids = set(participant_ids)
    all_ids.add(creator_id)
    all_ids.discard(user_id)
    for other_id in all_ids:
        try:
            await bot.send_message(
                other_id,
                _format_proposal_text(meeting, proposer_name),
                reply_markup=pending_meeting_keyboard(meeting.id),
            )
        except Exception as exc:
            logger.error(
                "Failed to send meeting proposal to %s for meeting %s: %s",
                other_id,
                meeting.id,
                exc,
            )

    await reply_func(
        "Предложение о созвоне отправлено, ожидаем подтверждения.",
        reply_markup=await _menu_kb(user_id),
    )


def _format_meeting_ref(meeting) -> str:
    """Short human-readable reference to a meeting for notifications."""
    date_str = ""
    if meeting.scheduled_at:
        try:
            date_str = meeting.scheduled_at.astimezone(MOSCOW_TZ).strftime(
                "%d.%m.%Y %H:%M MSK"
            )
        except Exception:
            pass
    topic = meeting.description or meeting.event_type or "созвон"
    if date_str:
        return f"созвон «{e(topic)}» на {date_str}"
    return f"созвон «{e(topic)}»"


def _format_edit_header(meeting) -> str:
    date_str = "—"
    if meeting.scheduled_at:
        try:
            date_str = meeting.scheduled_at.astimezone(MOSCOW_TZ).strftime(
                "%d.%m.%Y %H:%M MSK"
            )
        except Exception:
            date_str = meeting.scheduled_at.isoformat()
    desc = e(meeting.description) if meeting.description else "—"
    link = e(meeting.meeting_link) if meeting.meeting_link else "—"
    event_type = e(meeting.event_type) if meeting.event_type else "—"
    others = [
        p for p in meeting.participants if p.telegram_id != meeting.mentor_telegram_id
    ]
    if others:
        names = [f"{e(p.name)}" + format_username_display(p.username) for p in others]
        participants_str = ", ".join(names)
    else:
        participants_str = "—"
    return (
        f"✏️ <b>Редактирование созвона</b>\n\n"
        f"📅 Дата и время: {date_str}\n"
        f"📝 Описание: {desc}\n"
        f"🔗 Ссылка: {link}\n"
        f"📋 Тип: {event_type}\n"
        f"👥 Участники: {participants_str}\n\n"
        f"Выберите поле для редактирования:"
    )


async def _save_edit_and_return(user_id, state, reply_func, bot, **update_values):
    data = await state.get_data()
    meeting_id = data["edit_meeting_id"]
    await MeetingDAO.update(meeting_id, **update_values)
    await state.clear()

    _trigger_caldav_sync(meeting_id)

    meeting = await MeetingDAO.get_with_participants(meeting_id)
    if meeting:
        editor = await UserDAO.find_one_or_none(telegram_id=user_id)
        editor_name = editor.name if editor else "Неизвестный участник"
        human_fields = ", ".join(
            MEETING_FIELD_LABELS.get(k, k) for k in update_values.keys()
        )
        meeting_ref = _format_meeting_ref(meeting)
        for p in meeting.participants:
            if p.telegram_id == user_id:
                continue
            try:
                await bot.send_message(
                    p.telegram_id,
                    f"✏️ <b>{e(editor_name)}</b> изменил(а) {meeting_ref}: "
                    f"{e(human_fields)}.",
                )
            except Exception as exc:
                logger.error(
                    "Failed to notify %s about meeting %s edit: %s",
                    p.telegram_id,
                    meeting_id,
                    exc,
                )

    view = await prepare_meetings_view(
        user_id,
        hide_past=True,
        text_prefix="✅ Созвон обновлён.\n\n",
    )
    await reply_func(
        view.text,
        reply_markup=mentor_meetings_keyboard(view.visible, page=0, viewer_id=user_id),
    )


@router.callback_query(
    PermissionFilter(["manage_meetings"]),
    EditMeetingCB.filter(),
)
async def cb_edit_meeting(
    callback: CallbackQuery, callback_data: EditMeetingCB, state: FSMContext
):
    await callback.answer()
    meeting = await MeetingDAO.get_with_participants(callback_data.meeting_id)
    if not meeting:
        await safe_edit_text(
            callback,
            "Созвон не найден.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        return
    await state.update_data(edit_meeting_id=callback_data.meeting_id)
    await state.set_state(EditMeetingFSM.choosing_field)
    await safe_edit_text(
        callback,
        _format_edit_header(meeting),
        reply_markup=edit_meeting_fields_keyboard(),
    )


@router.callback_query(
    PermissionFilter(["manage_meetings"]),
    StateFilter(EditMeetingFSM.choosing_field),
    EditMeetingFieldCB.filter(),
)
async def cb_edit_field_chosen(
    callback: CallbackQuery, callback_data: EditMeetingFieldCB, state: FSMContext
):
    await callback.answer()
    field = callback_data.field

    if field == "datetime":
        await state.set_state(EditMeetingFSM.editing_datetime_date)
        await safe_edit_text(
            callback,
            "Выберите новую дату:",
            reply_markup=meeting_calendar_keyboard(datetime.now(MSK).date()),
        )
    elif field == "description":
        await state.set_state(EditMeetingFSM.editing_description)
        await safe_edit_text(
            callback,
            "Введите новое описание:",
            reply_markup=meeting_cancel_keyboard(),
        )
    elif field == "link":
        await state.set_state(EditMeetingFSM.editing_link)
        await safe_edit_text(
            callback,
            "Введите новую ссылку:",
            reply_markup=meeting_cancel_keyboard(),
        )
    elif field == "type":
        await state.set_state(EditMeetingFSM.editing_type)
        await safe_edit_text(
            callback,
            "Выберите новый тип встречи:",
            reply_markup=meeting_type_keyboard(),
        )
    elif field == "student":
        data = await state.get_data()
        meeting_id = data["edit_meeting_id"]
        meeting = await MeetingDAO.get_with_participants(meeting_id)
        current_ids = (
            {
                p.telegram_id
                for p in meeting.participants
                if p.telegram_id != meeting.mentor_telegram_id
            }
            if meeting
            else set()
        )
        mentees = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
        if not mentees:
            await safe_edit_text(
                callback,
                "У вас нет менти.",
                reply_markup=await _menu_kb(callback.from_user.id),
            )
            await state.clear()
            return
        await state.update_data(
            selected_participant_ids=list(current_ids), showing_all=False
        )
        await state.set_state(EditMeetingFSM.editing_student)
        await safe_edit_text(
            callback,
            "Вы��ерите участников:",
            reply_markup=meeting_participants_multiselect_keyboard(
                mentees, selected_ids=current_ids, show_all_button=True
            ),
        )


@router.message(
    PermissionFilter("manage_meetings"),
    StateFilter(EditMeetingFSM.editing_description),
)
async def msg_edit_description(message: Message, state: FSMContext):
    description = message.text.strip() if message.text else ""
    await _save_edit_and_return(
        message.from_user.id,
        state,
        message.answer,
        message.bot,
        description=description,
    )


@router.message(
    PermissionFilter("manage_meetings"),
    StateFilter(EditMeetingFSM.editing_link),
)
async def msg_edit_link(message: Message, state: FSMContext):
    link = message.text.strip() if message.text else ""
    await _save_edit_and_return(
        message.from_user.id,
        state,
        message.answer,
        message.bot,
        meeting_link=link or None,
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(EditMeetingFSM.editing_type),
    ChooseMeetingTypeCB.filter(),
)
async def cb_edit_type(
    callback: CallbackQuery, callback_data: ChooseMeetingTypeCB, state: FSMContext
):
    await callback.answer()
    from src.bot.keyboards.meeting import MEETING_TYPES

    if callback_data.type_idx >= len(MEETING_TYPES):
        await safe_edit_text(
            callback,
            "Неверный тип встречи.",
            reply_markup=await _menu_kb(callback.from_user.id),
        )
        await state.clear()
        return
    await _save_edit_and_return(
        callback.from_user.id,
        state,
        lambda text, **kw: safe_edit_text(callback, text, **kw),
        callback.bot,
        event_type=MEETING_TYPES[callback_data.type_idx],
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(EditMeetingFSM.editing_student),
    ToggleMeetingParticipantCB.filter(),
)
async def cb_edit_toggle_participant(
    callback: CallbackQuery,
    callback_data: ToggleMeetingParticipantCB,
    state: FSMContext,
):
    await callback.answer()
    data = await state.get_data()
    selected: list[int] = data.get("selected_participant_ids", [])
    uid = callback_data.user_id
    if uid in selected:
        selected.remove(uid)
    else:
        selected.append(uid)
    await state.update_data(selected_participant_ids=selected)

    showing_all = data.get("showing_all", False)
    if showing_all:
        users = await UserDAO.get_all()
    else:
        users = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    for attempt in range(3):
        try:
            await callback.message.edit_reply_markup(
                reply_markup=meeting_participants_multiselect_keyboard(
                    users, selected_ids=set(selected), show_all_button=not showing_all
                ),
            )
            break
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
            break
        except TelegramNetworkError:
            if attempt == 2:
                raise
            await asyncio.sleep(0.5)


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(EditMeetingFSM.editing_student),
    ShowAllUsersCB.filter(),
)
async def cb_edit_show_all_users(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    selected: list[int] = data.get("selected_participant_ids", [])
    await state.update_data(showing_all=True)
    users = await UserDAO.get_all()
    await callback.message.edit_reply_markup(
        reply_markup=meeting_participants_multiselect_keyboard(
            users, selected_ids=set(selected), show_all_button=False
        ),
    )


@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(EditMeetingFSM.editing_student),
    ConfirmParticipantSelectionCB.filter(),
)
async def cb_edit_confirm_participants(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    selected: list[int] = data.get("selected_participant_ids", [])
    if not selected:
        await callback.answer("Выберите хотя бы одного участника.", show_alert=True)
        return

    meeting_id = data["edit_meeting_id"]
    await MeetingDAO.update_participants(meeting_id, selected)

    _trigger_caldav_sync(meeting_id)

    # Update mentee_telegram_tag for Notion sync
    mentee_tags: list[str] = []
    for pid in selected:
        user = await UserDAO.find_one_or_none(telegram_id=pid)
        if user and user.username:
            mentee_tags.append(f"@{user.username}")
        elif user and user.name:
            mentee_tags.append(user.name)
    if mentee_tags:
        await MeetingDAO.update(meeting_id, mentee_telegram_tag=", ".join(mentee_tags))

    await state.clear()

    meeting = await MeetingDAO.get_with_participants(meeting_id)
    user_id = callback.from_user.id
    if meeting:
        editor = await UserDAO.find_one_or_none(telegram_id=user_id)
        editor_name = editor.name if editor else "Неизвестный участник"
        meeting_ref = _format_meeting_ref(meeting)
        for p in meeting.participants:
            if p.telegram_id == user_id:
                continue
            try:
                await callback.bot.send_message(
                    p.telegram_id,
                    f"✏️ <b>{e(editor_name)}</b> обновил(а) участников: {meeting_ref}.",
                )
            except Exception as exc:
                logger.error(
                    "Failed to notify %s about meeting %s edit: %s",
                    p.telegram_id,
                    meeting_id,
                    exc,
                )

    view = await prepare_meetings_view(
        user_id,
        hide_past=True,
        text_prefix="✅ Созвон обновлён.\n\n",
    )
    await safe_edit_text(
        callback,
        view.text,
        reply_markup=mentor_meetings_keyboard(view.visible, page=0, viewer_id=user_id),
    )


@router.message(
    PermissionFilter(["manage_meetings", "propose_meetings"]),
    StateFilter(CreateMeetingFSM.waiting_link),
)
async def msg_meeting_link(message: Message, state: FSMContext):
    link = message.text.strip() if message.text else ""
    await _finalize_meeting(
        user_id=message.from_user.id,
        state=state,
        link=link or None,
        reply_func=message.answer,
        bot=message.bot,
    )


@router.callback_query(PermissionFilter("manage_meetings"), DeleteMeetingCB.filter())
async def cb_delete_meeting(callback: CallbackQuery, callback_data: DeleteMeetingCB):
    await callback.answer()

    # Snapshot CalDAV links BEFORE the meeting row is deleted — afterwards
    # the FK cascade wipes them and we'd have nothing to DELETE remotely.
    await _trigger_caldav_delete(callback_data.meeting_id)

    deleted, notion_page_id = await MeetingDAO.delete_for_mentor(
        meeting_id=callback_data.meeting_id,
        user_id=callback.from_user.id,
    )

    if not deleted:
        await safe_edit_text(
            callback,
            "Созвон не найден или у вас нет прав на удаление.",
            reply_markup=mentor_meetings_keyboard(),
        )
        return

    if notion_page_id:
        from src.tasks.meeting import archive_notion_page

        archive_notion_page.delay(notion_page_id)

    if callback_data.source == "past":
        view = await prepare_meetings_view(
            callback.from_user.id,
            only_past=True,
            title="Завершённые созвоны:",
            text_prefix="Созвон удалён.\n\n",
        )
        await safe_edit_text(
            callback,
            view.text,
            reply_markup=mentor_past_meetings_keyboard(
                view.visible, page=0, viewer_id=callback.from_user.id
            ),
        )
    else:
        view = await prepare_meetings_view(
            callback.from_user.id,
            hide_past=True,
            text_prefix="Созвон удалён.\n\n",
        )
        await safe_edit_text(
            callback,
            view.text,
            reply_markup=mentor_meetings_keyboard(
                view.visible, page=0, viewer_id=callback.from_user.id
            ),
        )


async def _finalize_confirmation(
    meeting_id: int, user_id: int, bot: Bot, reply_func, state: FSMContext
) -> None:
    meeting, all_confirmed = await MeetingDAO.confirm_meeting(meeting_id, user_id)
    if not meeting:
        await reply_func(
            "Вы уже подтвердили или нет прав.",
            reply_markup=await _menu_kb(user_id),
        )
        return

    if meeting.original_scheduled_at and all_confirmed:
        meeting = await MeetingDAO.confirm_reschedule(meeting.id, user_id)

    if meeting:
        _trigger_caldav_sync(meeting.id)

    if all_confirmed and meeting:
        await _schedule_meeting_tasks(meeting)
        for p in meeting.participants:
            if p.telegram_id == user_id:
                continue
            try:
                await bot.send_message(p.telegram_id, "✅ Созвон подтверждён!")
            except Exception as exc:
                logger.error(
                    "Failed to notify %s about confirmation: %s", p.telegram_id, exc
                )
        await reply_func(
            "✅ Созвон подтверждён.",
            reply_markup=await _menu_kb(user_id),
        )
    else:
        await reply_func(
            "✅ Ваше подтверждение принято, ожидаем остальных участников.",
            reply_markup=await _menu_kb(user_id),
        )


@router.callback_query(ConfirmMeetingCB.filter())
async def cb_confirm_meeting(
    callback: CallbackQuery, callback_data: ConfirmMeetingCB, state: FSMContext
):
    await callback.answer()
    user_id = callback.from_user.id

    meeting = await MeetingDAO.get_with_participants(callback_data.meeting_id)
    if (
        meeting
        and meeting.proposal_status == ProposalStatus.pending_confirmation
        and meeting.meeting_link is None
        and meeting.original_scheduled_at is None
        and user_id == meeting.mentor_telegram_id
    ):
        await state.update_data(approve_meeting_id=meeting.id)
        await state.set_state(ApproveMeetingFSM.entering_link)
        await safe_edit_text(
            callback,
            "Введите ссылку на встречу (Telemost, Zoom, Google Meet и т.д.):",
            reply_markup=meeting_link_cancel_keyboard(),
        )
        return

    await _finalize_confirmation(
        callback_data.meeting_id,
        user_id,
        callback.bot,
        lambda text, **kw: safe_edit_text(callback, text, **kw),
        state,
    )


@router.message(
    PermissionFilter("manage_meetings"),
    StateFilter(ApproveMeetingFSM.entering_link),
)
async def msg_approve_meeting_link(message: Message, state: FSMContext):
    data = await state.get_data()
    meeting_id = data.get("approve_meeting_id")
    link = message.text.strip() if message.text else ""
    if not meeting_id or not link:
        await state.clear()
        await message.answer(
            "Не удалось подтвердить созвон. Попробуйте ещё раз.",
            reply_markup=await _menu_kb(message.from_user.id),
        )
        return

    await MeetingDAO.update(meeting_id, meeting_link=link)
    await state.clear()
    await _finalize_confirmation(
        meeting_id,
        message.from_user.id,
        message.bot,
        message.answer,
        state,
    )


@router.callback_query(DeclineMeetingCB.filter())
async def cb_decline_meeting(callback: CallbackQuery, callback_data: DeclineMeetingCB):
    await callback.answer()
    user_id = callback.from_user.id

    meeting = await MeetingDAO.get_with_participants(callback_data.meeting_id)
    if not meeting:
        await callback.answer("Встреча не найдена.", show_alert=True)
        return

    if meeting.original_scheduled_at:
        # Decline reschedule — revert to original time
        reverted = await MeetingDAO.decline_reschedule(
            callback_data.meeting_id, user_id
        )
        if reverted:
            _trigger_caldav_sync(reverted.id)
            for p in reverted.participants:
                if p.telegram_id == user_id:
                    continue
                try:
                    await callback.bot.send_message(
                        p.telegram_id,
                        "❌ Перенос отклонён. Созвон остаётся на прежнем времени.",
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to notify %s about decline: %s", p.telegram_id, exc
                    )
        await safe_edit_text(
            callback,
            "Перенос отклонён.",
            reply_markup=await _menu_kb(user_id),
        )
    else:
        # Decline new meeting proposal — delete it
        # Notify all participants before deleting
        for p in meeting.participants:
            if p.telegram_id == user_id:
                continue
            try:
                await callback.bot.send_message(
                    p.telegram_id, "❌ Предложение о созвоне отклонено."
                )
            except Exception as exc:
                logger.error(
                    "Failed to notify %s about decline: %s", p.telegram_id, exc
                )
        # Snapshot CalDAV links before the cascade wipes them.
        await _trigger_caldav_delete(callback_data.meeting_id)
        await MeetingDAO.decline_meeting(callback_data.meeting_id, user_id)
        await safe_edit_text(
            callback,
            "Предложение отклонено.",
            reply_markup=await _menu_kb(user_id),
        )


@router.callback_query(ProposeNewTimeCB.filter())
async def cb_propose_new_time(
    callback: CallbackQuery, callback_data: ProposeNewTimeCB, state: FSMContext
):
    await callback.answer()

    meeting = await MeetingDAO.get_with_participants(callback_data.meeting_id)
    if not meeting:
        await callback.answer("Встреча не найдена.", show_alert=True)
        return

    user_id = callback.from_user.id
    if user_id not in {p.telegram_id for p in meeting.participants}:
        await callback.answer("Нет доступа к этой встрече.", show_alert=True)
        return

    await state.update_data(
        reschedule_meeting_id=meeting.id,
    )
    await state.set_state(CreateMeetingFSM.waiting_date)
    await safe_edit_text(
        callback,
        "Выберите новую дату:",
        reply_markup=meeting_calendar_keyboard(datetime.now(MSK).date()),
    )


@router.callback_query(
    PermissionFilter(["manage_meetings", "propose_meetings"]),
    StateFilter(
        CreateMeetingFSM.choosing_student,
        CreateMeetingFSM.choosing_type,
        CreateMeetingFSM.waiting_description,
        CreateMeetingFSM.waiting_date,
        CreateMeetingFSM.waiting_time,
        CreateMeetingFSM.waiting_link,
        ApproveMeetingFSM.entering_link,
        EditMeetingFSM.choosing_field,
        EditMeetingFSM.editing_datetime_date,
        EditMeetingFSM.editing_datetime_time,
        EditMeetingFSM.editing_description,
        EditMeetingFSM.editing_link,
        EditMeetingFSM.editing_type,
        EditMeetingFSM.editing_student,
    ),
    F.data == "meeting_create_cancel",
)
async def cb_meeting_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await safe_edit_text(
        callback,
        "Отменено.",
        reply_markup=await _menu_kb(callback.from_user.id),
    )


# Pagination: participants multi-select
@router.callback_query(
    PermissionFilter("manage_meetings"),
    StateFilter(CreateMeetingFSM.choosing_student, EditMeetingFSM.editing_student),
    PageNavCB.filter(F.menu == "participants"),
)
async def cb_participants_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    data = await state.get_data()
    search_query = (data.get("_pagination_search") or {}).get("participants")
    selected: list[int] = data.get("selected_participant_ids", [])
    showing_all = data.get("showing_all", False)
    if showing_all:
        users = await UserDAO.get_all()
    else:
        users = await MenteeDAO.get_by_mentor_telegram_id(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=meeting_participants_multiselect_keyboard(
            users,
            selected_ids=set(selected),
            page=callback_data.page,
            show_all_button=not showing_all,
            search_query=search_query,
        )
    )


# Pagination: meetings list
@router.callback_query(
    PermissionFilter("manage_meetings"),
    PageNavCB.filter(F.menu == "meetings"),
)
async def cb_meetings_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    data = await state.get_data()
    search_query = (data.get("_pagination_search") or {}).get("meetings")
    page = callback_data.page
    view = await prepare_meetings_view(callback.from_user.id, hide_past=True, page=page)
    await safe_edit_text(
        callback,
        view.text,
        reply_markup=mentor_meetings_keyboard(
            view.visible,
            page=page,
            viewer_id=callback.from_user.id,
            search_query=search_query,
        ),
    )


# Past (completed) meetings
@router.callback_query(
    PermissionFilter("manage_meetings"), F.data == "past_meetings_mentor"
)
async def cb_mentor_past_meetings(callback: CallbackQuery):
    await callback.answer()
    view = await prepare_meetings_view(
        callback.from_user.id, only_past=True, title="Завершённые созвоны:"
    )
    await safe_edit_text(
        callback,
        view.text,
        reply_markup=mentor_past_meetings_keyboard(
            view.visible, page=0, viewer_id=callback.from_user.id
        ),
    )


@router.callback_query(
    PermissionFilter("view_own_meetings"), F.data == "past_meetings_student"
)
async def cb_student_past_meetings(callback: CallbackQuery):
    await callback.answer()
    view = await prepare_meetings_view(
        callback.from_user.id,
        only_past=True,
        viewer_is_mentor=False,
        title="Завершённые созвоны:",
    )
    await safe_edit_text(
        callback,
        view.text,
        reply_markup=student_past_meetings_keyboard(view.visible, page=0),
    )


# Pagination: past meetings list
@router.callback_query(
    PageNavCB.filter(F.menu == "past_meetings"),
)
async def cb_past_meetings_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    await callback.answer()
    data = await state.get_data()
    search_query = (data.get("_pagination_search") or {}).get("past_meetings")
    page = callback_data.page
    mentor_tg_ids = await MentorDAO.get_telegram_ids()
    is_mentor = callback.from_user.id in mentor_tg_ids
    view = await prepare_meetings_view(
        callback.from_user.id,
        only_past=True,
        viewer_is_mentor=is_mentor,
        page=page,
        title="Завершённые созвоны:",
    )
    if is_mentor:
        markup = mentor_past_meetings_keyboard(
            view.visible,
            page=page,
            viewer_id=callback.from_user.id,
            search_query=search_query,
        )
    else:
        markup = student_past_meetings_keyboard(
            view.visible, page=page, search_query=search_query
        )
    await safe_edit_text(callback, view.text, reply_markup=markup)
