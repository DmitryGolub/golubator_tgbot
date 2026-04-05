import logging
from string import Template

from aiogram.exceptions import TelegramForbiddenError

from src.models.trigger import TriggerRule
from src.services.events.actions.base import BaseAction
from src.utils.escape import e

logger = logging.getLogger(__name__)


class SendNotificationAction(BaseAction):
    async def execute(
        self,
        *,
        rule: TriggerRule,
        recipient_id: int,
        context: dict,
        bot,
    ) -> None:
        if recipient_id < 0:
            logger.debug("Skipping placeholder user %s", recipient_id)
            return

        text = rule.action_config.get("text", "")
        if not text:
            logger.warning("TriggerRule %s has empty notification text", rule.id)
            return

        if "$general_chat_link" in text or "$mentor_channel_link" in text:
            from src.services.invite_link import InviteLinkService

            invite_links = await InviteLinkService.generate_links_for_mentee(
                bot, recipient_id
            )
            context = {**context, **invite_links}

        safe_context = {k: e(v) for k, v in context.items()}
        try:
            text = Template(text).safe_substitute(safe_context)
        except (ValueError, TypeError):
            pass

        try:
            await bot.send_message(recipient_id, text, parse_mode="HTML")
        except TelegramForbiddenError:
            logger.warning(
                "User %s blocked the bot, skipping notification", recipient_id
            )
