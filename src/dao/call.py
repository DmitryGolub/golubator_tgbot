from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.call import Call, CallStatus


class CallDAO(BaseDAO):
    model = Call

    @classmethod
    async def get_active_for_mentor(cls, mentor_id: int) -> Optional[Call]:
        """Return the ongoing call where this user is the mentor, or None."""
        async with async_session_maker() as session:
            query = (
                select(Call)
                .where(Call.mentor_id == mentor_id, Call.status == CallStatus.ongoing)
                .order_by(Call.started_at.desc())
                .limit(1)
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def finish_call(cls, call_id: int, mentor_id: int) -> Optional[Call]:
        """
        Close the call only if it belongs to the given mentor and is still ongoing.
        Sets status=finished and ended_at=now().
        Returns the updated Call or None if not found / not allowed.
        """
        async with async_session_maker() as session:
            query = (
                update(Call)
                .where(
                    Call.id == call_id,
                    Call.mentor_id == mentor_id,
                    Call.status == CallStatus.ongoing,
                )
                .values(
                    status=CallStatus.finished,
                    ended_at=datetime.now(timezone.utc),
                )
                .returning(Call)
            )
            result = await session.execute(query)
            await session.commit()
            return result.scalar_one_or_none()
