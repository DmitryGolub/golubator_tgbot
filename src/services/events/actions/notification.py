import logging
from string import Template

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
        text = rule.action_config.get("text", "")
        if not text:
            logger.warning("TriggerRule %s has empty notification text", rule.id)
            return

        # Safe template substitution — no attribute access possible
        try:
            text = Template(text).safe_substitute(context)
        except (ValueError, TypeError):
            pass

        await bot.send_message(recipient_id, text, parse_mode="HTML")
