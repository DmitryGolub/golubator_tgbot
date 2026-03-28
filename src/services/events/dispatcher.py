import logging
from datetime import datetime, timedelta, timezone

from src.dao.trigger_execution import TriggerExecutionDAO
from src.dao.trigger_rule import TriggerRuleDAO
from src.models.trigger import ActionType, DelayMode, TriggerRule, TriggerType
from src.services.events.actions.notification import SendNotificationAction
from src.services.events.actions.survey import SendSurveyAction
from src.services.events.recipient_resolver import RecipientResolver

logger = logging.getLogger(__name__)

ACTION_MAP = {
    ActionType.send_notification: SendNotificationAction(),
    ActionType.send_survey: SendSurveyAction(),
}


class EventDispatcher:
    @classmethod
    async def emit(
        cls,
        trigger_type: TriggerType,
        context: dict,
        bot=None,
    ) -> None:
        """Dispatch event to all matching active trigger rules."""
        rules = await TriggerRuleDAO.get_active_by_trigger(trigger_type)
        if not rules:
            return

        logger.info("Event %s: %d rule(s) matched", trigger_type.value, len(rules))

        for rule in rules:
            try:
                await cls._process_rule(rule, context, bot)
            except Exception:
                logger.exception("Error processing TriggerRule %s", rule.id)

    @classmethod
    async def execute_rule_manually(
        cls,
        rule_id: int,
        context: dict,
        bot=None,
    ) -> int:
        """Execute a rule manually. Returns number of recipients."""
        rule = await TriggerRuleDAO.get_by_id(rule_id)
        if not rule:
            return 0

        recipients = await RecipientResolver.resolve(rule, context)
        for recipient_id in recipients:
            await cls.execute_action(rule, recipient_id, context, bot)

        return len(recipients)

    @classmethod
    async def _process_rule(
        cls,
        rule: TriggerRule,
        context: dict,
        bot,
    ) -> None:
        recipients = await RecipientResolver.resolve(rule, context)
        if not recipients:
            return

        logger.info(
            "Rule %s (%s): %d recipient(s)",
            rule.id,
            rule.action_type.value,
            len(recipients),
        )

        event_key = cls._build_event_key(rule, context)

        for recipient_id in recipients:
            if rule.delay_seconds == 0:
                # Immediate execution
                execution, already_existed = await TriggerExecutionDAO.create(
                    rule_id=rule.id,
                    event_key=event_key,
                    recipient_id=recipient_id,
                    context=context,
                )
                if already_existed:
                    continue

                try:
                    await cls.execute_action(rule, recipient_id, context, bot)
                    await TriggerExecutionDAO.mark_sent(execution.id)
                    logger.info("Rule %s executed for user %s", rule.id, recipient_id)
                except Exception as exc:
                    await TriggerExecutionDAO.mark_failed(execution.id, str(exc))
                    logger.error(
                        "Failed to execute rule %s for user %s: %s",
                        rule.id,
                        recipient_id,
                        exc,
                    )
            else:
                # Delayed execution via Celery
                eta = cls._calculate_eta(rule, context)
                execution, already_existed = await TriggerExecutionDAO.create(
                    rule_id=rule.id,
                    event_key=event_key,
                    recipient_id=recipient_id,
                    scheduled_at=eta,
                    context=context,
                )
                if already_existed:
                    continue

                from src.tasks.trigger import execute_trigger_action

                execute_trigger_action.apply_async(
                    args=[execution.id],
                    eta=eta,
                )
                logger.info(
                    "Scheduled trigger rule %s for user %s at %s",
                    rule.id,
                    recipient_id,
                    eta,
                )

    @classmethod
    async def execute_action(
        cls,
        rule: TriggerRule,
        recipient_id: int,
        context: dict,
        bot,
    ) -> None:
        action = ACTION_MAP.get(rule.action_type)
        if not action:
            raise ValueError(f"Unknown action_type: {rule.action_type}")

        await action.execute(
            rule=rule,
            recipient_id=recipient_id,
            context=context,
            bot=bot,
        )

    @classmethod
    def _build_event_key(cls, rule: TriggerRule, context: dict) -> str | None:
        trigger = rule.trigger_type

        if trigger == TriggerType.meeting_created:
            meeting_id = context.get("meeting_id", "")
            return f"meeting_created:{meeting_id}:{rule.id}"

        if trigger == TriggerType.call_ended:
            meeting_id = context.get("meeting_id", "")
            return f"call_ended:{meeting_id}:{rule.id}"

        if trigger == TriggerType.periodic_cron:
            now_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
            return f"periodic:{now_key}:{rule.id}"

        if trigger == TriggerType.manual:
            # No dedup for manual triggers
            return None

        return f"{trigger.value}:{rule.id}"

    @classmethod
    def _calculate_eta(cls, rule: TriggerRule, context: dict) -> datetime:
        now = datetime.now(timezone.utc)

        if rule.delay_mode == DelayMode.before_scheduled:
            scheduled_at = context.get("scheduled_at")
            if scheduled_at:
                if isinstance(scheduled_at, str):
                    scheduled_at = datetime.fromisoformat(scheduled_at)
                if scheduled_at.tzinfo is None:
                    from src.utils.tz import MSK

                    scheduled_at = scheduled_at.replace(tzinfo=MSK)
                eta = scheduled_at - timedelta(seconds=rule.delay_seconds)
                if eta > now:
                    return eta
                # If eta is in the past, execute immediately
                return now

        return now + timedelta(seconds=rule.delay_seconds)
