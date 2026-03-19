from typing import Optional

from sqlalchemy import select

from src.core.database import async_session_maker
from src.models.mentor_feedback import MentorFeedback


class MentorFeedbackDAO:
    @classmethod
    async def create(
        cls,
        *,
        call_id: int,
        mentor_id: int,
        status: str,
        duration: str,
        motivation: int,
        neuromutation_stage: int,
        comment: str | None,
    ) -> MentorFeedback:
        feedback = MentorFeedback(
            call_id=call_id,
            mentor_id=mentor_id,
            status=status,
            duration=duration,
            motivation=motivation,
            neuromutation_stage=neuromutation_stage,
            comment=comment,
        )

        async with async_session_maker() as session:
            async with session.begin():
                session.add(feedback)
                await session.flush()
            await session.refresh(feedback)
            return feedback

    @classmethod
    async def get_by_call_id(cls, call_id: int) -> Optional[MentorFeedback]:
        async with async_session_maker() as session:
            query = select(MentorFeedback).where(MentorFeedback.call_id == call_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def get_call_ids(cls, call_ids: list[int]) -> set[int]:
        if not call_ids:
            return set()

        async with async_session_maker() as session:
            query = select(MentorFeedback.call_id).where(MentorFeedback.call_id.in_(call_ids))
            result = await session.execute(query)
            return set(result.scalars().all())
