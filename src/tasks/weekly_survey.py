import logging
from collections import defaultdict
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.celery_app import celery_app
from src.core.config import settings
from src.tasks._db import celery_db, run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="surveys.send_weekly_mentor_per_student")
def send_weekly_mentor_per_student() -> None:
    """Send per-student weekly survey to each mentor whose student is in Study."""
    run_async(_send_weekly_mentor_per_student_async())


async def _send_weekly_mentor_per_student_async() -> None:
    async with celery_db():
        bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        try:
            from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
            from src.dao.cohort import CohortDAO
            from src.dao.mentee import MenteeDAO
            from src.dao.survey_template import SurveyTemplateDAO
            from src.services.survey_session import SurveySessionService
            from src.utils.escape import e

            template = await SurveyTemplateDAO.get_by_slug("weekly_mentor_per_student")
            if not template:
                logger.error("Template 'weekly_mentor_per_student' not found")
                return

            study_tids = await CohortDAO.get_telegram_ids_in_cohort("Status", "Study")
            if not study_tids:
                logger.info("No students in Study cohort, skipping mentor surveys")
                return

            mentees = await MenteeDAO.get_by_telegram_ids(study_tids)

            # Group by mentor telegram_id
            mentor_students: dict[int, list] = defaultdict(list)
            for mentee in mentees:
                if not mentee.mentor or not mentee.mentor.telegram_id:
                    continue
                if mentee.mentor.telegram_id < 0:
                    continue
                mentor_students[mentee.mentor.telegram_id].append(mentee)

            now = datetime.now(timezone.utc)
            year_week = now.strftime("%G-W%V")
            service = SurveySessionService()
            sent = 0
            skipped = 0

            for mentor_tid, students in mentor_students.items():
                for mentee in students:
                    student_tid = mentee.telegram_id
                    context_id = f"{year_week}:{student_tid}"

                    try:
                        session, already_existed = await service.create_session(
                            template_id=template.id,
                            respondent_id=mentor_tid,
                            context_type="weekly",
                            context_id=context_id,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to create session for mentor=%s student=%s",
                            mentor_tid,
                            student_tid,
                        )
                        continue

                    if already_existed:
                        skipped += 1
                        continue

                    student_name = (
                        mentee.user.name if mentee.user else mentee.doc_name or "Ученик"
                    )

                    kb = InlineKeyboardBuilder()
                    kb.button(
                        text="Пройти опрос",
                        callback_data=StartDynamicSurveyCB(session_id=session.id),
                    )

                    try:
                        await bot.send_message(
                            mentor_tid,
                            f"<b>Еженедельный опрос по ученику</b>\n\n"
                            f"Ученик: <b>{e(student_name)}</b>\n"
                            f"Пожалуйста, заполните опрос (~2 мин, 5 вопросов).",
                            reply_markup=kb.as_markup(),
                            parse_mode="HTML",
                        )
                        sent += 1
                    except TelegramForbiddenError:
                        logger.warning(
                            "Mentor %s blocked the bot, skipping survey", mentor_tid
                        )

            logger.info(
                "Weekly mentor surveys: sent=%d, skipped(dedup)=%d, mentors=%d",
                sent,
                skipped,
                len(mentor_students),
            )
        finally:
            await bot.session.close()
