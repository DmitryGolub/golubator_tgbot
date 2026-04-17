import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from src.bot.callbacks.feedback_report import (
    FeedbackRecipientCB,
    FeedbackTypeCB,
)
from src.bot.keyboards.feedback_report import (
    feedback_recipient_keyboard,
    feedback_type_keyboard,
)
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.middlewares.album_middleware import AlbumMiddleware
from src.bot.states.feedback_report import FeedbackReportFSM
from src.bot.utils import safe_edit_text
from src.dao.user import UserDAO
from src.services.ui_text import UiTextService

logger = logging.getLogger(__name__)

router = Router(name="feedback_report")
router.message.middleware(AlbumMiddleware())

CAPTION_LIMIT = 1024
MEDIA_GROUP_LIMIT = 10


@router.callback_query(F.data == "feedback_report_menu")
async def cb_feedback_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    text = await UiTextService.get("feedback.choose_type")
    await safe_edit_text(callback, text, reply_markup=feedback_type_keyboard())
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


@router.message(FeedbackReportFSM.entering_text)
async def msg_enter_text(
    message: Message,
    state: FSMContext,
    bot: Bot,
    album: list[Message] | None = None,
):
    source_msgs = album if album else [message]

    if album:
        source_msgs = sorted(album, key=lambda m: m.message_id)
        text = next((m.caption for m in source_msgs if m.caption), "")
    else:
        text = message.caption or message.text or ""

    attachments: list[dict] = []
    for m in source_msgs:
        if m.photo:
            attachments.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.video:
            attachments.append({"type": "video", "file_id": m.video.file_id})

    if not text and not attachments:
        await message.answer("Отправьте текст обращения или приложите фото/видео.")
        return

    sender = message.from_user
    if sender.username:
        username = f"@{sender.username}"
    else:
        username = sender.full_name or "Аноним"

    await state.update_data(
        text=text,
        attachments=attachments,
        sender={"username": username, "full_name": sender.full_name},
    )

    data = await state.get_data()
    if data["feedback_type"] == "problem":
        prompt = await UiTextService.get("feedback.choose_recipient")
        await message.answer(prompt, reply_markup=feedback_recipient_keyboard())
        await state.set_state(FeedbackReportFSM.choosing_recipient)
    else:
        await _send_bug_report(message, state, bot)


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
    attachments = data.get("attachments") or []

    sender = callback.from_user
    if sender.username:
        username = f"@{sender.username}"
    else:
        username = sender.full_name or "Аноним"
    full_name = sender.full_name
    outgoing = f"📩 Обращение от {username} ({full_name}):\n{text}"

    recipients = await UserDAO.get_all(role_name=callback_data.role)
    for user in recipients:
        if user.telegram_id < 0:
            continue
        await _deliver_safe(bot, user.telegram_id, outgoing, attachments)

    confirmation = await UiTextService.get("feedback.sent")
    await safe_edit_text(
        callback, confirmation, reply_markup=await back_to_menu_keyboard()
    )
    await state.clear()


async def _send_bug_report(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    text = data["text"]
    attachments = data.get("attachments") or []

    sender_data = data.get("sender") or {}
    username = sender_data.get("username", "")
    full_name = sender_data.get("full_name", "")
    outgoing = f"🐛 Баг-репорт от {username} ({full_name}):\n{text}"

    admins = await UserDAO.get_all(role_name="admin")
    for admin in admins:
        if admin.telegram_id < 0:
            continue
        await _deliver_safe(bot, admin.telegram_id, outgoing, attachments)

    confirmation = await UiTextService.get("feedback.bug_sent")
    await message.answer(confirmation, reply_markup=await back_to_menu_keyboard())
    await state.clear()


async def _deliver_safe(
    bot: Bot, chat_id: int, text: str, attachments: list[dict]
) -> None:
    try:
        await _deliver(bot, chat_id, text, attachments)
    except TelegramForbiddenError:
        logger.info("User %s blocked the bot, skipping feedback", chat_id)
    except TelegramBadRequest as exc:
        if "chat not found" in str(exc).lower():
            logger.info("Chat not found for user %s, skipping feedback", chat_id)
        else:
            logger.warning(
                "Failed to send feedback to %s: %s", chat_id, exc, exc_info=True
            )
    except Exception:
        logger.warning("Failed to send feedback to %s", chat_id, exc_info=True)


async def _deliver(bot: Bot, chat_id: int, text: str, attachments: list[dict]) -> None:
    if not attachments:
        await bot.send_message(chat_id, text)
        return

    attachments = attachments[:MEDIA_GROUP_LIMIT]

    if len(attachments) == 1:
        item = attachments[0]
        if len(text) <= CAPTION_LIMIT:
            if item["type"] == "photo":
                await bot.send_photo(chat_id, item["file_id"], caption=text)
            else:
                await bot.send_video(chat_id, item["file_id"], caption=text)
        else:
            await bot.send_message(chat_id, text)
            if item["type"] == "photo":
                await bot.send_photo(chat_id, item["file_id"])
            else:
                await bot.send_video(chat_id, item["file_id"])
        return

    media: list[InputMediaPhoto | InputMediaVideo] = []
    use_caption = len(text) <= CAPTION_LIMIT
    for i, item in enumerate(attachments):
        caption = text if (use_caption and i == 0) else None
        if item["type"] == "photo":
            media.append(InputMediaPhoto(media=item["file_id"], caption=caption))
        else:
            media.append(InputMediaVideo(media=item["file_id"], caption=caption))

    if not use_caption:
        await bot.send_message(chat_id, text)
    await bot.send_media_group(chat_id, media)
