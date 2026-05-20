import logging
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.states.dynamic_survey import DynamicSurveyFSM
from src.core.config import settings
from src.dao.survey_session import SurveySessionDAO

logger = logging.getLogger(__name__)

_CACHE_TTL = 5 if settings.TEST_MODE else 60
_MAX_CACHE = 10_000

# user_id -> (has_pending, timestamp)
_pending_cache: OrderedDict[int, tuple[bool, float]] = OrderedDict()

# user_id -> (chat_id, message_id) of the latest block-notice message
_block_msg: OrderedDict[int, tuple[int, int]] = OrderedDict()

_SURVEY_CALLBACK_PREFIXES = ("ds_start:", "ds_ans:")
_SURVEY_CALLBACK_EXACT = {"my_surveys"}


def invalidate_pending_cache(user_id: int) -> None:
    _pending_cache.pop(user_id, None)


def pop_block_message(user_id: int) -> tuple[int, int] | None:
    return _block_msg.pop(user_id, None)


class SurveyBlockMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = self._get_user_id(event)
        if user_id is None:
            return await handler(event, data)

        # Allow survey-related callbacks through
        if isinstance(event, CallbackQuery) and event.data:
            if event.data in _SURVEY_CALLBACK_EXACT or event.data.startswith(
                _SURVEY_CALLBACK_PREFIXES
            ):
                return await handler(event, data)

        # Allow if user is currently taking a survey (FSM state)
        state: FSMContext | None = data.get("state")
        if state:
            current_state = await state.get_state()
            if current_state in (
                DynamicSurveyFSM.answering.state,
                DynamicSurveyFSM.waiting_text.state,
            ):
                return await handler(event, data)

        # Check pending surveys (with cache)
        has_pending = await self._check_pending(user_id)
        if not has_pending:
            return await handler(event, data)

        # Block: send message with button to surveys
        logger.info("Blocking user %s: has pending survey(s)", user_id)

        # Delete previous block-notice (if any) to avoid accumulation
        bot = data.get("bot")
        old = _block_msg.pop(user_id, None)
        if old is not None and bot is not None:
            try:
                await bot.delete_message(chat_id=old[0], message_id=old[1])
            except TelegramBadRequest:
                pass

        kb = InlineKeyboardBuilder()
        kb.button(text="Перейти к опросам", callback_data="my_surveys")
        text = (
            "⚠️ У вас есть незаполненный опрос.\n"
            "Пожалуйста, завершите его, прежде чем продолжить."
        )

        sent: Message | None = None
        if isinstance(event, CallbackQuery):
            await event.answer()
            msg = event.message
            if isinstance(msg, Message):
                sent = await msg.answer(text, reply_markup=kb.as_markup())
            else:
                await event.answer(text, show_alert=True)
                return None
        elif isinstance(event, Message):
            sent = await event.answer(text, reply_markup=kb.as_markup())

        if sent is not None:
            _block_msg[user_id] = (sent.chat.id, sent.message_id)
            _block_msg.move_to_end(user_id)
            while len(_block_msg) > _MAX_CACHE:
                _block_msg.popitem(last=False)

        return None

    @staticmethod
    def _get_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, (Message, CallbackQuery)):
            return event.from_user.id if event.from_user else None
        return None

    @staticmethod
    async def _check_pending(user_id: int) -> bool:
        now = time.monotonic()
        cached = _pending_cache.get(user_id)
        if cached is not None:
            has_pending, ts = cached
            if now - ts < _CACHE_TTL:
                return has_pending

        try:
            sessions = await SurveySessionDAO.get_pending_for_respondent(user_id)
            has_pending = len(sessions) > 0
        except Exception:
            logger.warning(
                "Failed to check pending surveys for %s", user_id, exc_info=True
            )
            has_pending = False

        _pending_cache[user_id] = (has_pending, now)
        _pending_cache.move_to_end(user_id)
        while len(_pending_cache) > _MAX_CACHE:
            _pending_cache.popitem(last=False)

        return has_pending
