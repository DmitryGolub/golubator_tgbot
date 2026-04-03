import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError

from src.celery_app import celery_app
from src.core.config import settings
from src.tasks._db import celery_db, run_async

logger = logging.getLogger(__name__)

# Student stage (Status cohort value) -> role that receives alerts
STAGE_ROLE_MAP: dict[str, str] = {
    "greeting": "education_lead",
    "Study": "education_lead",
    "search": "job_search_lead",
    "offer": "job_search_lead",
    "Probationary period": "education_lead",
}


def _format_alert_message(alert) -> str:
    details = alert.details or {}
    slug = details.get("slug", "")
    alert_type = alert.alert_type.value

    student_name = "Неизвестен"
    if alert.student:
        student_name = alert.student.name or str(alert.student.telegram_id)

    respondent_name = "Неизвестен"
    if alert.session and alert.session.respondent:
        r = alert.session.respondent
        respondent_name = r.name or str(r.telegram_id)

    template_title = ""
    if alert.session and alert.session.template:
        template_title = alert.session.template.title

    if alert_type == "low_score":
        return (
            f"<b>Алёрт: низкая оценка</b>\n\n"
            f"Опрос: {template_title}\n"
            f"Респондент: {respondent_name}\n"
            f"Ученик: {student_name}\n"
            f"Вопрос: {details.get('question', '?')}\n"
            f"Оценка: <b>{details.get('score')}</b> "
            f"(порог: {details.get('threshold')})"
        )
    elif alert_type == "delta_decline":
        scores = details.get("scores", [])
        return (
            f"<b>Алёрт: падение оценок</b>\n\n"
            f"Опрос: {template_title}\n"
            f"Респондент: {respondent_name}\n"
            f"Ученик: {student_name}\n"
            f"Оценки (новые→старые): {' → '.join(str(s) for s in scores)}"
        )
    elif alert_type == "cross_mismatch":
        return (
            f"<b>Алёрт: расхождение оценок</b>\n\n"
            f"Ученик: {student_name}\n"
            f"Средняя оценка ({slug}): {details.get('avg_current')}\n"
            f"Средняя оценка ({details.get('paired_slug')}): "
            f"{details.get('avg_paired')}\n"
            f"Разница: <b>{details.get('diff')}</b>"
        )
    elif alert_type == "mentor_not_recommend":
        return (
            f"<b>Алёрт: ментор не рекомендует брать ученика</b>\n\n"
            f"Опрос: {template_title}\n"
            f"Ментор: {respondent_name}\n"
            f"Ученик: {student_name}"
        )
    else:
        return f"<b>Алёрт ({alert_type})</b>\n\nОпрос: {template_title}"


async def _process_survey_alerts_async() -> None:
    async with celery_db():
        bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        try:
            from src.dao.cohort import CohortDAO
            from src.dao.survey_alert import SurveyAlertDAO
            from src.dao.user import UserDAO

            alerts = await SurveyAlertDAO.get_unnotified()
            if not alerts:
                return

            logger.info("Processing %d unnotified survey alerts", len(alerts))
            sent = 0

            for alert in alerts:
                # Determine student stage -> role
                role_name = None
                student_id = alert.student_id
                if student_id:
                    statuses = await CohortDAO.get_user_cohort_values_by_type(
                        student_id, "Status"
                    )
                    for status in statuses:
                        role_name = STAGE_ROLE_MAP.get(status)
                        if role_name:
                            break

                if not role_name:
                    role_name = "education_lead"

                recipients = await UserDAO.get_all(role_name=role_name)
                message = _format_alert_message(alert)

                for user in recipients:
                    if user.telegram_id < 0:
                        continue
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            message,
                            parse_mode="HTML",
                        )
                        sent += 1
                    except TelegramForbiddenError:
                        logger.warning(
                            "User %s blocked the bot, skipping alert",
                            user.telegram_id,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to send alert %d to user %s",
                            alert.id,
                            user.telegram_id,
                        )

                await SurveyAlertDAO.mark_notified(alert.id)

            logger.info("Survey alerts processed: sent=%d messages", sent)
        finally:
            await bot.session.close()


@celery_app.task(name="surveys.process_alerts")
def process_survey_alerts() -> None:
    """Every 5 minutes: send notifications for unprocessed survey alerts."""
    run_async(_process_survey_alerts_async())
