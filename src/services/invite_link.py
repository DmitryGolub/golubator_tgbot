import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from src.core.config import settings
from src.dao.mentee import MenteeDAO

logger = logging.getLogger(__name__)

LINK_UNAVAILABLE = "(ссылка недоступна)"


class InviteLinkService:
    @staticmethod
    async def _create_one_time_link(bot: Bot, chat_id: int) -> str | None:
        try:
            link = await bot.create_chat_invite_link(chat_id=chat_id, member_limit=1)
            return link.invite_link
        except TelegramAPIError:
            logger.exception("Failed to create invite link for chat %s", chat_id)
            return None

    @classmethod
    async def general_chat_link(cls, bot: Bot) -> str:
        if not settings.GENERAL_CHAT_ID:
            return LINK_UNAVAILABLE
        link = await cls._create_one_time_link(bot, settings.GENERAL_CHAT_ID)
        return link or LINK_UNAVAILABLE

    @classmethod
    async def mentor_channel_link(cls, bot: Bot, mentee_telegram_id: int) -> str:
        mentee = await MenteeDAO.find_by_telegram_id(mentee_telegram_id)
        if mentee and mentee.mentor and mentee.mentor.channel_id:
            link = await cls._create_one_time_link(bot, mentee.mentor.channel_id)
            if link:
                return link
        return LINK_UNAVAILABLE

    @classmethod
    async def generate_links_for_mentee(
        cls, bot: Bot, mentee_telegram_id: int
    ) -> dict[str, str]:
        return {
            "general_chat_link": await cls.general_chat_link(bot),
            "mentor_channel_link": await cls.mentor_channel_link(
                bot, mentee_telegram_id
            ),
        }
