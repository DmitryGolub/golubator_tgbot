from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from src.core.database import async_session_maker
from src.models.trigger import TriggerRule, TriggerType


class TriggerRuleDAO:
    @classmethod
    async def get_all(cls) -> list[TriggerRule]:
        async with async_session_maker() as session:
            query = select(TriggerRule).order_by(TriggerRule.id)
            result = await session.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def get_all_active(cls) -> list[TriggerRule]:
        async with async_session_maker() as session:
            query = (
                select(TriggerRule)
                .where(TriggerRule.is_active.is_(True))
                .order_by(TriggerRule.id)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def get_active_by_trigger(
        cls, trigger_type: TriggerType
    ) -> list[TriggerRule]:
        async with async_session_maker() as session:
            query = (
                select(TriggerRule)
                .where(
                    TriggerRule.trigger_type == trigger_type,
                    TriggerRule.is_active.is_(True),
                )
                .order_by(TriggerRule.id)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def get_by_id(cls, rule_id: int) -> Optional[TriggerRule]:
        async with async_session_maker() as session:
            return await session.get(TriggerRule, rule_id)

    @classmethod
    async def create(cls, **data) -> TriggerRule:
        async with async_session_maker() as session:
            rule = TriggerRule(**data)
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    @classmethod
    async def delete(cls, rule_id: int) -> bool:
        async with async_session_maker() as session:
            rule = await session.get(TriggerRule, rule_id)
            if not rule:
                return False
            await session.delete(rule)
            await session.commit()
            return True

    @classmethod
    async def set_active(cls, rule_id: int, is_active: bool) -> Optional[TriggerRule]:
        async with async_session_maker() as session:
            rule = await session.get(TriggerRule, rule_id)
            if not rule:
                return None
            rule.is_active = is_active
            await session.commit()
            await session.refresh(rule)
            return rule

    @classmethod
    async def update(cls, rule_id: int, **fields) -> Optional[TriggerRule]:
        async with async_session_maker() as session:
            rule = await session.get(TriggerRule, rule_id)
            if not rule:
                return None
            for key, value in fields.items():
                setattr(rule, key, value)
            rule.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(rule)
            return rule
