import logging
from string import Template

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from src.models.survey_template import SurveyTemplate
from src.utils.escape import e

logger = logging.getLogger(__name__)


async def send_broadcast_message(
    bot,
    recipient_id: int,
    template: SurveyTemplate,
    context: dict | None = None,
) -> bool:
    """Render template.body and send it as HTML message.

    Supports $general_chat_link / $mentor_channel_link placeholders.
    Returns True if the message was delivered, False if it was skipped
    (blocked bot / missing chat / empty body).
    """
    if recipient_id < 0:
        logger.debug("Skipping placeholder user %s", recipient_id)
        return False

    body = template.body or ""
    if not body:
        logger.warning(
            "Broadcast template %s (%s) has empty body", template.id, template.slug
        )
        return False

    ctx = dict(context or {})
    needs_general = "$general_chat_link" in body
    needs_mentor = "$mentor_channel_link" in body
    if needs_general or needs_mentor:
        from src.services.invite_link import InviteLinkService

        if needs_general:
            ctx["general_chat_link"] = await InviteLinkService.general_chat_link(bot)
        if needs_mentor:
            ctx["mentor_channel_link"] = await InviteLinkService.mentor_channel_link(
                bot, recipient_id
            )

    safe_context = {k: e(v) for k, v in ctx.items()}
    try:
        text = Template(body).safe_substitute(safe_context)
    except (ValueError, TypeError):
        text = body

    try:
        await bot.send_message(recipient_id, text, parse_mode="HTML")
        return True
    except TelegramForbiddenError:
        logger.warning("User %s blocked the bot, skipping", recipient_id)
    except TelegramBadRequest as exc:
        if "chat not found" in str(exc).lower():
            logger.warning("Chat not found for user %s, skipping", recipient_id)
        else:
            raise
    return False
