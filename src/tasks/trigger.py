import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from src.celery_app import celery_app
from src.core.config import settings
from src.tasks._db import celery_db, run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="triggers.execute_action")
def execute_trigger_action(execution_id: int) -> None:
    """Execute a single delayed trigger action."""
    run_async(_execute_action_async(execution_id))


@celery_app.task(name="triggers.tick_periodic")
def tick_periodic_triggers() -> None:
    """Check and fire periodic trigger rules. Runs every minute via beat."""
    run_async(_tick_periodic_async())


@celery_app.task(name="triggers.process_pending")
def process_pending_executions() -> None:
    """Pick up pending executions that were missed (e.g. worker restart)."""
    run_async(_process_pending_async())


async def _execute_action_async(execution_id: int) -> None:
    async with celery_db():
        bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        try:
            from src.dao.trigger_execution import TriggerExecutionDAO
            from src.dao.trigger_rule import TriggerRuleDAO
            from src.services.events.dispatcher import EventDispatcher

            from src.core.database import async_session_maker

            async with async_session_maker() as session:
                from src.models.trigger import TriggerExecution, ExecutionStatus

                exec_obj = await session.get(TriggerExecution, execution_id)
                if not exec_obj:
                    logger.warning("TriggerExecution %s not found", execution_id)
                    return
                if exec_obj.status != ExecutionStatus.pending:
                    return
                rule_id = exec_obj.rule_id
                recipient_id = exec_obj.recipient_id
                exec_context = exec_obj.context or {}

            rule = await TriggerRuleDAO.get_by_id(rule_id)
            if not rule:
                await TriggerExecutionDAO.mark_failed(execution_id, "Rule not found")
                return

            try:
                await EventDispatcher.execute_action(
                    rule=rule,
                    recipient_id=recipient_id,
                    context=exec_context,
                    bot=bot,
                )
                await TriggerExecutionDAO.mark_sent(execution_id)
                logger.info(
                    "Trigger execution %s completed: rule=%s user=%s",
                    execution_id,
                    rule_id,
                    recipient_id,
                )
            except Exception as exc:
                await TriggerExecutionDAO.mark_failed(execution_id, str(exc))
                logger.exception("Failed trigger execution %s", execution_id)
        finally:
            await bot.session.close()


async def _tick_periodic_async() -> None:
    async with celery_db():
        bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        try:
            from src.dao.trigger_rule import TriggerRuleDAO
            from src.models.trigger import TriggerType
            from src.services.events.dispatcher import EventDispatcher

            rules = await TriggerRuleDAO.get_active_by_trigger(
                TriggerType.periodic_cron
            )
            now = datetime.now(timezone.utc)

            fired = 0
            for rule in rules:
                if _should_fire_now(rule, now):
                    try:
                        await EventDispatcher.fire_rule(
                            rule,
                            {"rule_id": rule.id},
                            bot=bot,
                        )
                        fired += 1
                    except Exception:
                        logger.exception("Error firing periodic rule %s", rule.id)

            if fired:
                logger.info("Periodic triggers: %d/%d fired", fired, len(rules))
        finally:
            await bot.session.close()


async def _process_pending_async() -> None:
    async with celery_db():
        bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        try:
            from src.dao.trigger_execution import TriggerExecutionDAO
            from src.dao.trigger_rule import TriggerRuleDAO
            from src.services.events.dispatcher import EventDispatcher

            pending = await TriggerExecutionDAO.get_pending_due()
            if pending:
                logger.info("Processing %d pending execution(s)", len(pending))
            for execution in pending:
                rule = await TriggerRuleDAO.get_by_id(execution.rule_id)
                if not rule:
                    await TriggerExecutionDAO.mark_failed(
                        execution.id, "Rule not found"
                    )
                    continue

                try:
                    await EventDispatcher.execute_action(
                        rule=rule,
                        recipient_id=execution.recipient_id,
                        context=execution.context or {},
                        bot=bot,
                    )
                    await TriggerExecutionDAO.mark_sent(execution.id)
                except Exception as exc:
                    await TriggerExecutionDAO.mark_failed(execution.id, str(exc))
                    logger.exception("Failed pending execution %s", execution.id)
        finally:
            await bot.session.close()


def _should_fire_now(rule, now: datetime) -> bool:
    """Check if a periodic rule should fire at current minute."""
    if rule.cron_expression:
        return _match_cron(rule.cron_expression, now)

    if rule.regularity:
        return _match_regularity(rule, now)

    return False


def _match_cron(expr: str, now: datetime) -> bool:
    """Simple cron expression matching: 'minute hour day_of_month month day_of_week'."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return False

    checks = [
        (parts[0], now.minute),
        (parts[1], now.hour),
        (parts[2], now.day),
        (parts[3], now.month),
        (
            parts[4],
            now.isoweekday() % 7,
        ),  # isoweekday: Mon=1..Sun=7 → 0=Sun,1=Mon..6=Sat (cron convention)
    ]

    for pattern, value in checks:
        if not _match_cron_field(pattern, value):
            return False

    return True


def _match_cron_field(pattern: str, value: int) -> bool:
    if pattern == "*":
        return True

    # Handle */N
    if pattern.startswith("*/"):
        try:
            step = int(pattern[2:])
            return value % step == 0
        except ValueError:
            return False

    # Handle comma-separated values and ranges
    for part in pattern.split(","):
        try:
            if "-" in part:
                lo, hi = part.split("-", 1)
                if int(lo) <= value <= int(hi):
                    return True
            elif int(part) == value:
                return True
        except ValueError:
            pass

    return False


def _match_regularity(rule, now: datetime) -> bool:
    """Match regularity enum + time_of_day."""
    from src.models.enums import Regularity

    if rule.time_of_day:
        if now.hour != rule.time_of_day.hour or now.minute != rule.time_of_day.minute:
            return False
    else:
        # Default: fire at 09:00 UTC
        if now.hour != 9 or now.minute != 0:
            return False

    if rule.regularity == Regularity.day:
        return True
    if rule.regularity == Regularity.week:
        return now.weekday() == 0  # Monday
    if rule.regularity == Regularity.fortnight:
        # Fire on even ISO weeks
        return now.weekday() == 0 and now.isocalendar()[1] % 2 == 0
    if rule.regularity == Regularity.month:
        return now.day == 1

    return False
