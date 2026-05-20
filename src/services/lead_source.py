import logging
import secrets

from src.dao.lead_source import LeadSourceDAO
from src.dao.user import UserDAO
from src.models.lead_source import LeadSource, LeadSourceType

logger = logging.getLogger(__name__)

REF_PREFIX = "ref_"
CH_PREFIX = "ch_"


class LeadSourceService:
    @staticmethod
    async def get_or_create_referral_link(
        telegram_id: int, bot_username: str
    ) -> tuple[str, int]:
        """Return (deep_link_url, referral_count) for the user's stable referral link."""
        source = await LeadSourceDAO.find_referral_by_user(telegram_id)
        if source is None:
            code = f"{REF_PREFIX}{telegram_id}"
            source = await LeadSourceDAO.add(
                source_type=LeadSourceType.referral,
                code=code,
                created_by=telegram_id,
            )

        count = await LeadSourceDAO.count_referrals(source.id)
        link = f"https://t.me/{bot_username}?start={source.code}"
        return link, count

    @staticmethod
    async def create_channel_link(admin_id: int, label: str, bot_username: str) -> str:
        """Create a new channel link and return the deep link URL."""
        code = f"{CH_PREFIX}{secrets.token_urlsafe(6)}"
        await LeadSourceDAO.add(
            source_type=LeadSourceType.channel,
            code=code,
            label=label,
            created_by=admin_id,
        )
        return f"https://t.me/{bot_username}?start={code}"

    @staticmethod
    async def resolve_and_record(
        telegram_id: int,
        payload: str,
    ) -> LeadSource | None:
        """Parse deep link payload, record lead_source_id if user doesn't have one yet.

        Returns the resolved LeadSource or None.
        """
        if not payload:
            return None

        source = await LeadSourceDAO.find_by_code(payload)
        if source is None:
            logger.warning("Unknown deep link payload: %s", payload)
            return None

        if (
            source.source_type == LeadSourceType.referral
            and source.created_by == telegram_id
        ):
            return None

        # Record lead source only if user doesn't already have one
        user = await UserDAO.find_one_or_none(telegram_id=telegram_id)
        if user and user.lead_source_id is None:
            await UserDAO.update(telegram_id=telegram_id, lead_source_id=source.id)
            logger.info(
                "Lead source recorded: user=%s source=%s type=%s",
                telegram_id,
                source.code,
                source.source_type,
            )

        return source
