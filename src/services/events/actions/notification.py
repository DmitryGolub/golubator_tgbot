import html
import logging
from string import Template

from aiogram.exceptions import TelegramForbiddenError

from src.models.trigger import TriggerRule
from src.services.events.actions.base import BaseAction

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

        # Safe template substitution — no attribute access possible
        try:
            text = Template(text).safe_substitute(context)
        except (ValueError, TypeError):
            pass

        text = html.escape(text)

        try:
            await bot.send_message(recipient_id, text, parse_mode="HTML")
        except TelegramForbiddenError:
            logger.warning(
                "User %s blocked the bot, skipping notification", recipient_id
            )
