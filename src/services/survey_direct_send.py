import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.dynamic_survey import StartDynamicSurveyCB
from src.services.survey_session import SurveySessionService
from src.utils.escape import e

logger = logging.getLogger(__name__)


class SurveyDirectSendService:
    @staticmethod
    async def send_survey(
        *,
        template_id: int,
        template_title: str,
        recipient_type: str,
        recipient_config: dict,
        bot: Bot,
    ) -> int:
        recipient_ids = await _resolve_recipients(recipient_type, recipient_config)
        if not recipient_ids:
            return 0

        context_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        service = SurveySessionService()
        sent = 0

        for uid in recipient_ids:
            if uid < 0:
                continue
            try:
                session, already_existed = await service.create_session(
                    template_id=template_id,
                    respondent_id=uid,
                    context_type="manual_send",
                    context_id=context_id,
                )
                if already_existed:
                    continue

                kb = InlineKeyboardBuilder()
                kb.button(
                    text="Пройти опрос",
                    callback_data=StartDynamicSurveyCB(session_id=session.id),
                )
                await bot.send_message(
                    uid,
                    f"<b>{e(template_title)}</b>\n\nВам доступен новый опрос.",
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML",
                )
                sent += 1
            except TelegramForbiddenError:
                logger.warning("User %s blocked the bot, skipping", uid)
            except TelegramBadRequest as exc:
                if "chat not found" in str(exc).lower():
                    logger.warning("Chat not found for user %s, skipping", uid)
                else:
                    logger.exception("Failed to send survey to user %s", uid)
            except Exception:
                logger.exception("Failed to send survey to user %s", uid)

        return sent


async def _resolve_recipients(recipient_type: str, config: dict) -> list[int]:
    if recipient_type == "specific_users":
        return [int(uid) for uid in config.get("user_ids", [])]

    if recipient_type == "by_role":
        from src.dao.user import UserDAO

        role_name = config.get("role_name")
        if not role_name:
            return []
        users = await UserDAO.get_all(role_name=role_name)
        return [u.telegram_id for u in users if u.telegram_id > 0]

    if recipient_type == "by_state":
        from src.dao.cohort import CohortDAO

        state = config.get("state")
        if not state:
            return []
        return await CohortDAO.get_telegram_ids_in_cohort("Status", state)

    if recipient_type == "by_cohort":
        from src.dao.cohort import CohortDAO

        cohort_type = config.get("cohort_type", "Category")
        cohort_value = config.get("cohort_value")
        if not cohort_value:
            return []
        return await CohortDAO.get_telegram_ids_in_cohort(cohort_type, cohort_value)

    logger.warning("Unknown recipient_type: %s", recipient_type)
    return []
