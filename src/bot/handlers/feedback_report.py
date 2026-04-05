import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.feedback_report import (
    FeedbackRecipientCB,
    FeedbackSkipPhotoCB,
    FeedbackTypeCB,
)
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.states.feedback_report import FeedbackReportFSM
from src.bot.utils import safe_edit_text
from src.dao.user import UserDAO
from src.services.ui_text import UiTextService

logger = logging.getLogger(__name__)

router = Router(name="feedback_report")


@router.callback_query(F.data == "feedback_report_menu")
async def cb_feedback_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    text = await UiTextService.get("feedback.choose_type")
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Проблема или предложение", callback_data=FeedbackTypeCB(value="problem")
    )
    kb.button(text="Баг-репорт", callback_data=FeedbackTypeCB(value="bug"))
    kb.adjust(1)
    await safe_edit_text(callback, text, reply_markup=kb.as_markup())
    await state.set_state(FeedbackReportFSM.choosing_type)


@router.callback_query(FeedbackReportFSM.choosing_type, FeedbackTypeCB.filter())
async def cb_choose_type(
    callback: CallbackQuery, callback_data: FeedbackTypeCB, state: FSMContext
):
    await callback.answer()
    await state.update_data(feedback_type=callback_data.value)
    text = await UiTextService.get("feedback.enter_text")
    await safe_edit_text(callback, text, reply_markup=await back_to_menu_keyboard())
    await state.set_state(FeedbackReportFSM.entering_text)


@router.message(FeedbackReportFSM.entering_text, F.text)
async def msg_enter_text(message: Message, state: FSMContext):
    sender = message.from_user
    username = f"@{sender.username}" if sender.username else f"id{sender.id}"
    await state.update_data(
        text=message.text,
        sender={"username": username, "full_name": sender.full_name},
    )
    data = await state.get_data()

    if data["feedback_type"] == "problem":
        text = await UiTextService.get("feedback.choose_recipient")
        kb = InlineKeyboardBuilder()
        kb.button(text="Координатор", callback_data=FeedbackRecipientCB(role="admin"))
        kb.button(
            text="Лид направления",
            callback_data=FeedbackRecipientCB(role="direction_lead"),
        )
        kb.button(
            text="Лид по сопровождению",
            callback_data=FeedbackRecipientCB(role="education_lead"),
        )
        kb.button(
            text="Лид по поиску работы",
            callback_data=FeedbackRecipientCB(role="job_search_lead"),
        )
        kb.adjust(1)
        await message.answer(text, reply_markup=kb.as_markup())
        await state.set_state(FeedbackReportFSM.choosing_recipient)
    else:
        text = await UiTextService.get("feedback.attach_photo")
        kb = InlineKeyboardBuilder()
        kb.button(text="Пропустить", callback_data=FeedbackSkipPhotoCB())
        kb.adjust(1)
        await message.answer(text, reply_markup=kb.as_markup())
        await state.set_state(FeedbackReportFSM.waiting_photo)


@router.callback_query(
    FeedbackReportFSM.choosing_recipient, FeedbackRecipientCB.filter()
)
async def cb_choose_recipient(
    callback: CallbackQuery,
    callback_data: FeedbackRecipientCB,
    state: FSMContext,
    bot: Bot,
):
    await callback.answer()
    data = await state.get_data()
    text = data["text"]

    sender = callback.from_user
    username = f"@{sender.username}" if sender.username else f"id{sender.id}"
    full_name = sender.full_name
    outgoing = f"📩 Обращение от {username} ({full_name}):\n{text}"

    recipients = await UserDAO.get_all(role_name=callback_data.role)
    for user in recipients:
        try:
            await bot.send_message(user.telegram_id, outgoing)
        except Exception:
            logger.warning(
                "Failed to send feedback to %s", user.telegram_id, exc_info=True
            )

    confirmation = await UiTextService.get("feedback.sent")
    await safe_edit_text(
        callback, confirmation, reply_markup=await back_to_menu_keyboard()
    )
    await state.clear()


@router.message(FeedbackReportFSM.waiting_photo, F.photo)
async def msg_photo(message: Message, state: FSMContext, bot: Bot):
    photo_file_id = message.photo[-1].file_id
    await _send_bug_report(message, state, bot, photo_file_id=photo_file_id)


@router.callback_query(FeedbackReportFSM.waiting_photo, FeedbackSkipPhotoCB.filter())
async def cb_skip_photo(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await _send_bug_report(callback.message, state, bot, photo_file_id=None, edit=True)


async def _send_bug_report(
    message: Message,
    state: FSMContext,
    bot: Bot,
    *,
    photo_file_id: str | None,
    edit: bool = False,
):
    data = await state.get_data()
    text = data["text"]

    # Retrieve sender info from FSM data (stored at text-entry step)
    # The message object here may be the bot's own message if edit=True,
    # so we stored sender_id/username in state during entering_text.
    sender_data = data.get("sender") or {}
    username = sender_data.get("username", "")
    full_name = sender_data.get("full_name", "")
    outgoing = f"🐛 Баг-репорт от {username} ({full_name}):\n{text}"

    admins = await UserDAO.get_all(role_name="admin")
    for admin in admins:
        try:
            if photo_file_id:
                await bot.send_photo(admin.telegram_id, photo_file_id, caption=outgoing)
            else:
                await bot.send_message(admin.telegram_id, outgoing)
        except Exception:
            logger.warning(
                "Failed to send bug report to %s", admin.telegram_id, exc_info=True
            )

    confirmation = await UiTextService.get("feedback.bug_sent")
    if edit:
        await message.edit_text(
            confirmation, reply_markup=await back_to_menu_keyboard()
        )
    else:
        await message.answer(confirmation, reply_markup=await back_to_menu_keyboard())
    await state.clear()
