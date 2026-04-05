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
    async def generate_links_for_mentee(
        cls, bot: Bot, mentee_telegram_id: int
    ) -> dict[str, str]:
        result: dict[str, str] = {}

        # General chat link
        if settings.GENERAL_CHAT_ID:
            link = await cls._create_one_time_link(bot, settings.GENERAL_CHAT_ID)
            result["general_chat_link"] = link or LINK_UNAVAILABLE
        else:
            result["general_chat_link"] = LINK_UNAVAILABLE

        # Mentor channel link
        result["mentor_channel_link"] = LINK_UNAVAILABLE
        mentee = await MenteeDAO.find_by_telegram_id(mentee_telegram_id)
        if mentee and mentee.mentor and mentee.mentor.channel_id:
            link = await cls._create_one_time_link(bot, mentee.mentor.channel_id)
            if link:
                result["mentor_channel_link"] = link

        return result
