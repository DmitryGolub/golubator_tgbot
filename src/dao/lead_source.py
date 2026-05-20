from sqlalchemy import func, or_, select

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.lead_source import LeadSource, LeadSourceType
from src.models.user import User


class LeadSourceDAO(BaseDAO):
    model = LeadSource

    @classmethod
    async def find_by_code(cls, code: str) -> LeadSource | None:
        async with async_session_maker() as session:
            query = select(LeadSource).where(LeadSource.code == code)
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def find_referral_by_user(cls, telegram_id: int) -> LeadSource | None:
        async with async_session_maker() as session:
            query = select(LeadSource).where(
                LeadSource.source_type == LeadSourceType.referral,
                LeadSource.created_by == telegram_id,
            )
            result = await session.execute(query)
            return result.scalars().one_or_none()

    @classmethod
    async def count_referrals(cls, source_id: int) -> int:
        async with async_session_maker() as session:
            query = (
                select(func.count())
                .select_from(User)
                .where(User.lead_source_id == source_id)
            )
            result = await session.execute(query)
            return result.scalar_one()

    @classmethod
    async def get_channel_links(
        cls, page: int = 0, page_size: int = 6, search: str | None = None
    ) -> tuple[list[LeadSource], int]:
        async with async_session_maker() as session:
            base_filter = LeadSource.source_type == LeadSourceType.channel
            conditions = [base_filter]
            if search:
                pattern = f"%{search}%"
                conditions.append(
                    or_(
                        LeadSource.label.ilike(pattern),
                        LeadSource.code.ilike(pattern),
                    )
                )

            count_q = select(func.count()).select_from(LeadSource).where(*conditions)
            total = (await session.execute(count_q)).scalar_one()
            total_pages = max(1, (total + page_size - 1) // page_size)

            query = (
                select(LeadSource)
                .where(*conditions)
                .order_by(LeadSource.created_at.desc())
                .offset(page * page_size)
                .limit(page_size)
            )
            result = await session.execute(query)
            return list(result.scalars().all()), total_pages
