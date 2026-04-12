import logging

from src.dao.user import UserDAO
from src.models.trigger import RecipientType, TriggerRule

logger = logging.getLogger(__name__)


class RecipientResolver:
    @classmethod
    async def resolve(cls, rule: TriggerRule, context: dict) -> list[int]:
        """Resolve recipient user IDs based on rule config and event context."""
        rt = rule.recipient_type
        config = rule.recipient_config or {}

        if rt == RecipientType.event_student:
            student_id = context.get("student_id")
            return [student_id] if student_id else []

        if rt == RecipientType.event_mentor:
            mentor_id = context.get("mentor_id")
            return [mentor_id] if mentor_id else []

        if rt == RecipientType.event_user:
            uid = context.get("user_telegram_id")
            return [uid] if uid else []

        if rt == RecipientType.event_participants:
            participant_ids = context.get("participant_ids", [])
            return [int(pid) for pid in participant_ids]

        if rt == RecipientType.specific_users:
            user_ids = config.get("user_ids", [])
            return [int(uid) for uid in user_ids]

        if rt == RecipientType.by_role:
            role_name = config.get("role_name")
            if not role_name:
                logger.warning("TriggerRule %s: by_role without role_name", rule.id)
                return []
            users = await UserDAO.get_all(role_name=role_name)
            return [u.telegram_id for u in users]

        if rt == RecipientType.by_state:
            state = config.get("state")
            if not state:
                logger.warning("TriggerRule %s: by_state without state", rule.id)
                return []
            from src.dao.cohort import CohortDAO

            return await CohortDAO.get_telegram_ids_in_cohort("Status", state)

        if rt == RecipientType.direction_lead:
            student_id = context.get("student_id")
            if not student_id:
                return []
            from src.dao.cohort import CohortDAO

            return await CohortDAO.get_direction_leads_for_student(student_id)

        if rt == RecipientType.by_cohort:
            cohort_type = config.get("cohort_type", "Category")
            cohort_value = config.get("cohort_value")
            if not cohort_value:
                logger.warning(
                    "TriggerRule %s: by_cohort without cohort_value", rule.id
                )
                return []
            from src.dao.cohort import CohortDAO

            return await CohortDAO.get_telegram_ids_in_cohort(cohort_type, cohort_value)

        logger.warning("Unknown recipient_type: %s", rt)
        return []
