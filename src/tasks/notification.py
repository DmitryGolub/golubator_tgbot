import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from sqlalchemy import select, update, delete
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.celery_app import celery_app
from src.core.config import settings
from src.models.notification import Notification
from src.models.rule import UserRule, StateRule, CohortRule, Regularity
from src.models.user import User

logger = logging.getLogger(__name__)

REGULARITY_TO_DELTA = {
    Regularity.day: timedelta(days=1),
    Regularity.week: timedelta(days=7),
    Regularity.fortnight: timedelta(days=14),
    Regularity.month: timedelta(days=30),
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_within_bounds(now: datetime, start_at: datetime | None, end_at: datetime | None) -> bool:
    if start_at and now < start_at:
        return False
    if end_at and now > end_at:
        return False
    return True


async def _create_notifications_for_user_rules(now: datetime) -> int:
    """Create notifications for individual user rules."""
    created = 0
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            result = await session.execute(
                select(UserRule).options(joinedload(UserRule.user))
            )
            rules: Iterable[UserRule] = result.scalars().all()

            for rule in rules:
                delta = REGULARITY_TO_DELTA.get(rule.regularity)
                if not delta:
                    continue
                if not _is_within_bounds(now, rule.start_at, rule.end_at):
                    continue
                if rule.last_sent_at and rule.last_sent_at + delta > now:
                    continue

                session.add(
                    Notification(
                        user_id=rule.user_id,
                        text=rule.text,
                        scheduled_at=now,
                    )
                )
                rule.last_sent_at = now
                created += 1

            await session.commit()
    finally:
        await engine.dispose()
    if created:
        logger.info("Created %s notifications from user rules", created)
    return created


async def _create_notifications_for_state_rules(now: datetime) -> int:
    """Create notifications for rules that target user state."""
    created = 0
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            result = await session.execute(select(StateRule))
            rules: Iterable[StateRule] = result.scalars().all()

            for rule in rules:
                rule_created = 0
                delta = REGULARITY_TO_DELTA.get(rule.regularity)
                if not delta:
                    continue

                # throttle by rule periodicity
                if rule.last_sent_at and rule.last_sent_at + delta > now:
                    continue

                offset = timedelta(days=rule.offset_days or 0)

                users_result = await session.execute(
                    select(User).where(User.state == rule.user_state)
                )
                users: Iterable[User] = users_result.scalars().all()

                for user in users:
                    if not user.state_changed_at:
                        continue
                    first_allowed = user.state_changed_at + offset
                    if now < first_allowed:
                        continue
                    session.add(
                        Notification(
                            user_id=user.telegram_id,
                            text=rule.text,
                            scheduled_at=now,
                        )
                    )
                    created += 1
                    rule_created += 1

                if rule_created:
                    # mark rule as sent for this period so we don't re-create every minute
                    await session.execute(
                        update(StateRule)
                        .where(StateRule.id == rule.id)
                        .values(last_sent_at=now)
                    )

            await session.commit()
    finally:
        await engine.dispose()
    if created:
        logger.info("Created %s notifications from state rules", created)
    return created


async def _create_notifications_for_cohort_rules(now: datetime) -> int:
    """Create notifications for rules that target cohorts."""
    created = 0
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            result = await session.execute(
                select(CohortRule).options(joinedload(CohortRule.cohort))
            )
            rules: Iterable[CohortRule] = result.scalars().all()

            for rule in rules:
                delta = REGULARITY_TO_DELTA.get(rule.regularity)
                if not delta:
                    continue
                if rule.last_sent_at and rule.last_sent_at + delta > now:
                    continue

                users_result = await session.execute(
                    select(User).where(User.cohort_id == rule.cohort_id)
                )
                users: Iterable[User] = users_result.scalars().all()
                if not users:
                    continue

                for user in users:
                    session.add(
                        Notification(
                            user_id=user.telegram_id,
                            text=rule.text,
                            scheduled_at=now,
                        )
                    )
                    created += 1

                await session.execute(
                    update(CohortRule)
                    .where(CohortRule.id == rule.id)
                    .values(last_sent_at=now)
                )

            await session.commit()
    finally:
        await engine.dispose()
    if created:
        logger.info("Created %s notifications from cohort rules", created)
    return created


async def _generate_notifications() -> None:
    now = _now_utc()
    await _create_notifications_for_user_rules(now)
    await _create_notifications_for_state_rules(now)
    await _create_notifications_for_cohort_rules(now)


async def _send_due_notifications() -> None:
    now = _now_utc()
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            result = await session.execute(
                select(Notification)
                .where((Notification.scheduled_at == None) | (Notification.scheduled_at <= now))  # noqa: E711
            )
            notifications: list[Notification] = list(result.scalars().all())
    finally:
        await engine.dispose()

    if not notifications:
        return

    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    sent_ids: list[int] = []

    try:
        for notification in notifications:
            try:
                await bot.send_message(notification.user_id, notification.text)
                sent_ids.append(notification.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to send notification id=%s user=%s: %s",
                    notification.id,
                    notification.user_id,
                    exc,
                )
    finally:
        await bot.session.close()

    if sent_ids:
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with Session() as session:
                await session.execute(
                    delete(Notification).where(Notification.id.in_(sent_ids))
                )
                await session.commit()
        finally:
            await engine.dispose()
        logger.info("Sent and removed %s notifications", len(sent_ids))


async def _tick_notifications() -> None:
    """Single entrypoint to avoid concurrent rule/send tasks on shared pool."""
    await _generate_notifications()
    await _send_due_notifications()


def _run(coro) -> None:
    """Run coroutine on a fresh event loop per task (avoids cross-loop issues)."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    finally:
        loop.close()
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass


@celery_app.task(name="notifications.generate")
def generate_notifications() -> None:
    _run(_generate_notifications())


@celery_app.task(name="notifications.send_due")
def send_due_notifications() -> None:
    _run(_send_due_notifications())


@celery_app.task(name="notifications.tick")
def tick_notifications() -> None:
    _run(_tick_notifications())
