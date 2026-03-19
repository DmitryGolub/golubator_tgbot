from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.call import Call, CallStatus


class CallDAO(BaseDAO):
    model = Call

    @classmethod
    async def get_active_for_mentor(cls, mentor_id: int) -> Optional[Call]:
        async with async_session_maker() as session:
            query = (
                select(Call)
                .where(Call.mentor_id == mentor_id, Call.status == CallStatus.ongoing)
                .options(joinedload(Call.meeting))
                .order_by(Call.started_at.desc())
                .limit(1)
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def get_by_meeting_id(cls, meeting_id: int) -> Optional[Call]:
        async with async_session_maker() as session:
            query = (
                select(Call)
                .where(Call.meeting_id == meeting_id)
                .options(joinedload(Call.meeting))
                .order_by(Call.started_at.desc())
                .limit(1)
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def create_for_meeting(
        cls,
        *,
        meeting_id: int,
        mentor_id: int,
        student_id: int,
    ) -> Call:
        return await cls.add(
            meeting_id=meeting_id,
            mentor_id=mentor_id,
            student_id=student_id,
            status=CallStatus.ongoing,
        )

    @classmethod
    async def finish_call(cls, call_id: int, mentor_id: int) -> Optional[Call]:
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
