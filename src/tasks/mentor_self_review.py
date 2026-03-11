import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.celery_app import celery_app
from src.core.config import settings
from src.dao.mentor_self_review import MentorSelfReviewDAO

logger = logging.getLogger(__name__)


def _current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _start_review_keyboard(period: str):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Заполнить самооценку",
        callback_data=f"mentor_self_review:start:{period}",
    )
    kb.adjust(1)
    return kb.as_markup()


async def _trigger_monthly_self_review_async() -> None:
    period = _current_period()
    mentors = await MentorSelfReviewDAO.get_mentors_without_review_for_period(period)

    if not mentors:
        logger.info("Mentor self review trigger skipped: no mentors without review for %s", period)
        return

    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    sent = 0

    try:
        for mentor in mentors:
            try:
                await bot.send_message(
                    mentor.telegram_id,
                    "<b>Ежемесячная самооценка ментора</b>\n"
                    f"Период: <b>{period}</b>\n"
                    "Пожалуйста, заполните короткую форму.",
                    reply_markup=_start_review_keyboard(period),
                )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to send mentor self-review trigger to mentor=%s for period=%s: %s",
                    mentor.telegram_id,
                    period,
                    exc,
                )
    finally:
        await bot.session.close()

    logger.info(
        "Mentor self-review trigger finished for period=%s, recipients=%s",
        period,
        sent,
    )


@celery_app.task(name="mentor_self_review.trigger_monthly")
def trigger_monthly_self_review() -> None:
    asyncio.run(_trigger_monthly_self_review_async())
