import logging
from collections import defaultdict
from datetime import datetime, timezone

from aiogram.exceptions import TelegramAPIError
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.celery_app import celery_app
from src.tasks._db import celery_db, get_worker_bot, run_async

logger = logging.getLogger(__name__)


async def _send_mentor_survey_batch(
    *,
    template_slug: str,
    cohort_type: str,
    cohort_value: str,
    context_type: str,
    title: str,
    log_prefix: str,
    biweekly: bool = False,
) -> None:
    """Common logic for per-student mentor survey tasks."""
    now = datetime.now(timezone.utc)
    if biweekly and now.isocalendar()[1] % 2 != 0:
        logger.info(
            "Odd ISO week %d, skipping %s surveys",
            now.isocalendar()[1],
            log_prefix,
        )
        return

    async with celery_db():
        bot = get_worker_bot()
        from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
        from src.dao.cohort import CohortDAO
        from src.dao.mentee import MenteeDAO
        from src.dao.survey_template import SurveyTemplateDAO
        from src.services.survey_session import SurveySessionService
        from src.utils.escape import e

        template = await SurveyTemplateDAO.get_by_slug(template_slug)
        if not template:
            logger.error("Template '%s' not found", template_slug)
            return

        tids = await CohortDAO.get_telegram_ids_in_cohort(cohort_type, cohort_value)
        if not tids:
            logger.info(
                "No students in %s/%s cohort, skipping %s",
                cohort_type,
                cohort_value,
                log_prefix,
            )
            return

        mentees = await MenteeDAO.get_by_telegram_ids(tids)

        mentor_students: dict[int, list] = defaultdict(list)
        for mentee in mentees:
            if not mentee.mentor or not mentee.mentor.telegram_id:
                continue
            if mentee.mentor.telegram_id < 0:
                continue
            mentor_students[mentee.mentor.telegram_id].append(mentee)

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
                        context_type=context_type,
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
                    mentee.user.name if mentee.user else mentee.doc_name or "Менти"
                )

                kb = InlineKeyboardBuilder()
                kb.button(
                    text="Пройти опрос",
                    callback_data=StartDynamicSurveyCB(session_id=session.id),
                )

                try:
                    await bot.send_message(
                        mentor_tid,
                        f"<b>{e(title)}</b>\n\n"
                        f"Менти: <b>{e(student_name)}</b>\n"
                        f"Пожалуйста, заполните опрос (~2 мин, 5 вопросов).",
                        reply_markup=kb.as_markup(),
                        parse_mode="HTML",
                    )
                    sent += 1
                except TelegramAPIError:
                    logger.warning(
                        "Mentor %s blocked the bot, skipping survey", mentor_tid
                    )

        logger.info(
            "%s surveys: sent=%d, skipped(dedup)=%d, mentors=%d",
            log_prefix,
            sent,
            skipped,
            len(mentor_students),
        )


@celery_app.task(name="surveys.send_weekly_mentor_per_student")
def send_weekly_mentor_per_student() -> None:
    """Send per-student weekly survey to each mentor whose student is in Study."""
    run_async(
        _send_mentor_survey_batch(
            template_slug="weekly_mentor_per_student",
            cohort_type="Status",
            cohort_value="Study",
            context_type="weekly",
            title="Еженедельный опрос по менти",
            log_prefix="Weekly mentor",
        )
    )


@celery_app.task(name="surveys.send_search_biweekly_mentor")
def send_search_biweekly_mentor() -> None:
    """Send per-student biweekly survey to each mentor whose student is in search."""
    run_async(
        _send_mentor_survey_batch(
            template_slug="search_mentor_biweekly",
            cohort_type="Status",
            cohort_value="search",
            context_type="search_biweekly",
            title="Опрос по менти в поиске работы",
            log_prefix="Search biweekly mentor",
            biweekly=True,
        )
    )


@celery_app.task(name="surveys.send_probation_biweekly_mentee")
def send_probation_biweekly_mentee() -> None:
    """Send biweekly survey to each mentee in Probationary period."""
    run_async(_send_probation_biweekly_mentee_async())


async def _send_probation_biweekly_mentee_async() -> None:
    now = datetime.now(timezone.utc)
    if now.isocalendar()[1] % 2 != 0:
        logger.info(
            "Odd ISO week %d, skipping probation biweekly mentee surveys",
            now.isocalendar()[1],
        )
        return

    async with celery_db():
        bot = get_worker_bot()
        from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
        from src.dao.cohort import CohortDAO
        from src.dao.mentee import MenteeDAO
        from src.dao.survey_template import SurveyTemplateDAO
        from src.services.survey_session import SurveySessionService

        template = await SurveyTemplateDAO.get_by_slug("probation_mentee_biweekly")
        if not template:
            logger.error("Template 'probation_mentee_biweekly' not found")
            return

        prob_tids = await CohortDAO.get_telegram_ids_in_cohort(
            "Status", "Probationary period"
        )
        if not prob_tids:
            logger.info(
                "No students in Probationary period cohort, skipping mentee surveys"
            )
            return

        mentees = await MenteeDAO.get_by_telegram_ids(prob_tids)

        year_week = now.strftime("%G-W%V")
        service = SurveySessionService()
        sent = 0
        skipped = 0

        for mentee in mentees:
            mentee_tid = mentee.telegram_id
            if mentee_tid < 0:
                continue

            context_id = year_week

            try:
                session, already_existed = await service.create_session(
                    template_id=template.id,
                    respondent_id=mentee_tid,
                    context_type="probation_biweekly",
                    context_id=context_id,
                )
            except Exception:
                logger.exception("Failed to create session for mentee=%s", mentee_tid)
                continue

            if already_existed:
                skipped += 1
                continue

            kb = InlineKeyboardBuilder()
            kb.button(
                text="Пройти опрос",
                callback_data=StartDynamicSurveyCB(session_id=session.id),
            )

            try:
                await bot.send_message(
                    mentee_tid,
                    "<b>Опрос по испытательному сроку</b>\n\n"
                    "Пожалуйста, заполните опрос (~2 мин, 5 вопросов).",
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML",
                )
                sent += 1
            except TelegramAPIError:
                logger.warning("Mentee %s blocked the bot, skipping survey", mentee_tid)

        logger.info(
            "Probation biweekly mentee surveys: sent=%d, skipped(dedup)=%d, mentees=%d",
            sent,
            skipped,
            len(mentees),
        )


@celery_app.task(name="surveys.send_probation_biweekly_mentor")
def send_probation_biweekly_mentor() -> None:
    """Send per-student biweekly survey to each mentor whose student is in Probationary period."""
    run_async(
        _send_mentor_survey_batch(
            template_slug="probation_mentor_biweekly",
            cohort_type="Status",
            cohort_value="Probationary period",
            context_type="probation_biweekly_mentor",
            title="Опрос по менти на испытательном сроке",
            log_prefix="Probation biweekly mentor",
            biweekly=True,
        )
    )
