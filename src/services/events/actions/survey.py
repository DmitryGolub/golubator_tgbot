import logging

from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
from src.models.trigger import TriggerRule
from src.services.events.actions.base import BaseAction
from src.services.survey_session import SurveySessionService

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
        template_id = rule.action_config.get("survey_template_id")
        if not template_id:
            logger.warning("TriggerRule %s missing survey_template_id", rule.id)
            return

        context_type = context.get("context_type")
        context_id = context.get("context_id")

        # Auto-detect context from event
        if not context_type and "meeting_id" in context:
            context_type = "meeting"
            context_id = str(context["meeting_id"])

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
                template_id, recipient_id,
            )
            return

        kb = InlineKeyboardBuilder()
        kb.button(
            text="Пройти опрос",
            callback_data=StartDynamicSurveyCB(session_id=session.id),
        )

        template_title = rule.action_config.get("survey_title", "Опрос")
        await bot.send_message(
            recipient_id,
            f"<b>{template_title}</b>\n\nВам доступен новый опрос.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
