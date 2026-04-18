import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.celery_app import celery_app
from src.tasks._db import celery_db, get_worker_bot, run_async
from src.tasks.survey_alerts import STAGE_ROLE_MAP

logger = logging.getLogger(__name__)

REMINDER_AFTER_HOURS = 24
MENTOR_NOTIFY_AFTER_HOURS = 72
ESCALATE_AFTER_HOURS = 96


async def _check_survey_escalations_async() -> None:
    async with celery_db():
        bot = get_worker_bot()
        from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
        from src.dao.survey_session import SurveySessionDAO
        from src.dao.user import UserDAO
        from src.utils.escape import e

        overdue = await SurveySessionDAO.get_overdue_sessions(
            min_age_hours=REMINDER_AFTER_HOURS
        )
        if not overdue:
            return

        now = datetime.now(timezone.utc)
        logger.info("Checking %d overdue survey sessions", len(overdue))
        reminders = 0
        mentor_notifs = 0
        escalations = 0

        for survey_session in overdue:
            try:
                age = now - survey_session.created_at
                template_title = ""
                if survey_session.template:
                    template_title = survey_session.template.title
                respondent_id = survey_session.respondent_id

                # Skip placeholder respondents (synthetic negative IDs)
                if respondent_id < 0:
                    continue

                # Step 1: Reminder after 24h
                if (
                    age > timedelta(hours=REMINDER_AFTER_HOURS)
                    and survey_session.reminder_sent_at is None
                ):
                    kb = InlineKeyboardBuilder()
                    kb.button(
                        text="Пройти опрос",
                        callback_data=StartDynamicSurveyCB(
                            session_id=survey_session.id
                        ),
                    )
                    try:
                        await bot.send_message(
                            respondent_id,
                            f"⚠️ <b>Незаполненный опрос</b>\n\n"
                            f"Опрос «{e(template_title)}» ожидает вашего ответа.\n"
                            f"Заполнение опроса — обязательная часть программы.\n\n"
                            f"Если опрос не будет заполнен в ближайшее время, "
                            f"информация будет передана вашему ментору.",
                            reply_markup=kb.as_markup(),
                            parse_mode="HTML",
                        )
                        reminders += 1
                        await SurveySessionDAO.update_escalation_field(
                            survey_session.id, "reminder_sent_at", now
                        )
                    except TelegramForbiddenError:
                        logger.warning(
                            "User %s blocked the bot (reminder), "
                            "will notify mentor immediately",
                            respondent_id,
                        )
                        # Bot blocked -> notify mentor right away
                        await _notify_mentor(
                            bot,
                            survey_session,
                            template_title,
                            blocked=True,
                        )
                        await SurveySessionDAO.update_escalation_field(
                            survey_session.id, "mentor_notified_at", now
                        )
                        await SurveySessionDAO.update_escalation_field(
                            survey_session.id, "reminder_sent_at", now
                        )
                        mentor_notifs += 1
                    except TelegramBadRequest as err:
                        logger.warning(
                            "Cannot send reminder to %s: %s",
                            respondent_id,
                            err,
                        )
                        # Dead chat -> mark reminder as sent to avoid loop
                        await SurveySessionDAO.update_escalation_field(
                            survey_session.id, "reminder_sent_at", now
                        )

                # Step 2: Notify mentor after 72h
                if (
                    age > timedelta(hours=MENTOR_NOTIFY_AFTER_HOURS)
                    and survey_session.mentor_notified_at is None
                ):
                    await _notify_mentor(
                        bot, survey_session, template_title, blocked=False
                    )
                    await SurveySessionDAO.update_escalation_field(
                        survey_session.id, "mentor_notified_at", now
                    )
                    mentor_notifs += 1

                # Step 3: Escalate to lead after 96h
                if (
                    age > timedelta(hours=ESCALATE_AFTER_HOURS)
                    and survey_session.escalated_at is None
                ):
                    role_name = await _resolve_role(respondent_id)
                    recipients = await UserDAO.get_all(role_name=role_name)

                    respondent_name = str(respondent_id)
                    if survey_session.respondent:
                        respondent_name = (
                            survey_session.respondent.name or respondent_name
                        )

                    for user in recipients:
                        if user.telegram_id < 0:
                            continue
                        try:
                            await bot.send_message(
                                user.telegram_id,
                                f"<b>Эскалация: неотвеченный опрос</b>\n\n"
                                f"Пользователь {e(respondent_name)} не ответил "
                                f"на опрос «{e(template_title)}» "
                                f"более {ESCALATE_AFTER_HOURS} часов.",
                                parse_mode="HTML",
                            )
                        except TelegramForbiddenError:
                            pass
                        except Exception:
                            logger.exception(
                                "Failed to escalate to user %s",
                                user.telegram_id,
                            )

                    await SurveySessionDAO.update_escalation_field(
                        survey_session.id, "escalated_at", now
                    )
                    escalations += 1
            except Exception:
                logger.exception(
                    "Failed to process overdue survey session %s",
                    survey_session.id,
                )

        logger.info(
            "Escalation check done: reminders=%d, mentor_notifs=%d, escalations=%d",
            reminders,
            mentor_notifs,
            escalations,
        )


async def _notify_mentor(
    bot: Bot,
    survey_session,
    template_title: str,
    *,
    blocked: bool,
) -> None:
    from src.dao.mentee import MenteeDAO
    from src.utils.escape import e

    respondent_id = survey_session.respondent_id
    mentee = await MenteeDAO.find_by_telegram_id(respondent_id)
    if not mentee or not mentee.mentor:
        return

    mentor = mentee.mentor
    if not mentor.telegram_id or mentor.telegram_id < 0:
        return

    respondent_name = str(respondent_id)
    if survey_session.respondent:
        respondent_name = survey_session.respondent.name or respondent_name

    reason = " (бот заблокирован)" if blocked else ""
    try:
        await bot.send_message(
            mentor.telegram_id,
            f"<b>Менти не ответил(а) на опрос</b>\n\n"
            f"Ваш менти {e(respondent_name)} не заполнил(а) опрос "
            f"«{e(template_title)}»{reason}.\n"
            f"Пожалуйста, напомните ему.",
            parse_mode="HTML",
        )
    except TelegramForbiddenError:
        logger.warning("Mentor %s blocked the bot", mentor.telegram_id)
    except TelegramBadRequest as err:
        logger.warning("Cannot notify mentor %s: %s", mentor.telegram_id, err)


async def _resolve_role(respondent_id: int) -> str:
    from src.dao.cohort import CohortDAO

    statuses = await CohortDAO.get_user_cohort_values_by_type(respondent_id, "Status")
    for status in statuses:
        role = STAGE_ROLE_MAP.get(status)
        if role:
            return role
    return "education_lead"


@celery_app.task(name="surveys.check_escalations")
def check_survey_escalations() -> None:
    """Every 2 minutes: check unanswered surveys and escalate."""
    run_async(_check_survey_escalations_async())
