import logging
from datetime import datetime, timezone

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
from src.dao.survey_session import SurveySessionDAO
from src.dao.survey_template import SurveyTemplateDAO
from src.models.survey_template import TemplateKind
from src.models.trigger import TriggerRule, TriggerType
from src.services.broadcast_sender import send_broadcast_message
from src.services.events.actions.base import BaseAction
from src.services.survey_session import SurveySessionService
from src.utils.escape import e

logger = logging.getLogger(__name__)


class SendSurveyAction(BaseAction):
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

        template_id = rule.action_config.get("survey_template_id")
        if not template_id:
            logger.warning("TriggerRule %s missing survey_template_id", rule.id)
            return

        template = await SurveyTemplateDAO.get_by_id(template_id)
        if not template:
            logger.warning(
                "TriggerRule %s references unknown template_id=%s",
                rule.id,
                template_id,
            )
            return

        context_type = context.get("context_type")
        context_id = context.get("context_id")

        # Auto-detect context from event
        if not context_type and "meeting_id" in context:
            context_type = "meeting"
            context_id = str(context["meeting_id"])

        # Periodic triggers: unique context per firing so dedup doesn't block repeats
        if not context_type and rule.trigger_type == TriggerType.periodic_cron:
            context_type = "periodic"
            context_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")

        service = SurveySessionService()
        session, already_existed = await service.create_session(
            template_id=template_id,
            respondent_id=recipient_id,
            context_type=context_type,
            context_id=context_id,
        )

        if already_existed:
            logger.info(
                "Survey session already exists for template=%s user=%s",
                template_id,
                recipient_id,
            )
            return

        # Broadcasts: send text, mark session complete+non-escalatable.
        if template.kind == TemplateKind.broadcast:
            await send_broadcast_message(bot, recipient_id, template, context)
            await SurveySessionDAO.update_escalation_field(
                session.id, "is_escalatable", False
            )
            await SurveySessionDAO.complete(session.id)
            return

        # Mark non-escalatable if configured (e.g. one-off notifications)
        if rule.action_config.get("escalatable") is False:
            await SurveySessionDAO.update_escalation_field(
                session.id, "is_escalatable", False
            )

        kb = InlineKeyboardBuilder()
        kb.button(
            text="Пройти опрос",
            callback_data=StartDynamicSurveyCB(session_id=session.id),
        )

        template_title = rule.action_config.get("survey_title") or template.title
        try:
            await bot.send_message(
                recipient_id,
                f"<b>{e(template_title)}</b>\n\nВам доступен новый опрос.",
                reply_markup=kb.as_markup(),
                parse_mode="HTML",
            )
        except TelegramForbiddenError:
            logger.warning("User %s blocked the bot, skipping", recipient_id)
        except TelegramBadRequest as exc:
            if "chat not found" in str(exc).lower():
                logger.warning("Chat not found for user %s, skipping", recipient_id)
            else:
                raise
