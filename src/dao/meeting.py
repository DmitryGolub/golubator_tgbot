from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, insert, delete, text, update
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.meeting import Meeting, MeetingUser


class MeetingDAO(BaseDAO):
    model = Meeting

    @classmethod
    async def create_with_participants(
        cls,
        *,
        description: str | None,
        meeting_link: str | None,
        scheduled_at: datetime | None,
        mentor_id: int,
        student_id: int,
    ) -> Meeting:
        async with async_session_maker() as session:
            meeting_stmt = (
                insert(Meeting)
                .values(
                    description=description,
                    meeting_link=meeting_link,
                    scheduled_at=scheduled_at,
                )
                .returning(Meeting)
            )
            meeting_res = await session.execute(meeting_stmt)
            meeting: Meeting = meeting_res.scalar_one()

            participants_stmt = insert(MeetingUser).values(
                [
                    {"meeting_id": meeting.id, "user_id": mentor_id},
                    {"meeting_id": meeting.id, "user_id": student_id},
                ]
            )
            await session.execute(participants_stmt)
            await session.commit()

            # reload with participants
            query = (
                select(Meeting)
                .where(Meeting.id == meeting.id)
                .options(joinedload(Meeting.participants))
            )
            result = await session.execute(query)
            result = result.unique()
            return result.scalar_one()

    @classmethod
    async def get_for_user(cls, user_id: int, *, hide_past: bool = False) -> list[Meeting]:
        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(MeetingUser.user_id == user_id)
                .options(joinedload(Meeting.participants))
                .order_by(Meeting.created_at.desc())
            )
            if hide_past:
                now = datetime.now(timezone.utc)
                query = query.where((Meeting.scheduled_at - text("interval '3 hours'")) > now)
            res = await session.execute(query)
            res = res.unique()
            return res.scalars().all()

    @classmethod
    async def get_with_participants(cls, meeting_id: int) -> Optional[Meeting]:
        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .where(Meeting.id == meeting_id)
                .options(joinedload(Meeting.participants))
            )
            res = await session.execute(query)
            res = res.unique()
            return res.scalar_one_or_none()

    @classmethod
    async def delete_for_mentor(cls, meeting_id: int, mentor_id: int) -> bool:
        async with async_session_maker() as session:
            # ensure mentor is participant of meeting
            query = (
                select(Meeting)
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(Meeting.id == meeting_id, MeetingUser.user_id == mentor_id)
            )
            result = await session.execute(query)
            meeting = result.scalar_one_or_none()
            if not meeting:
                return False

            await session.execute(delete(Meeting).where(Meeting.id == meeting_id))
            await session.commit()
            return True

    @classmethod
    async def purge_older_than(cls, cutoff: datetime) -> int:
        # Deprecated name: now marks meetings as completed instead of deleting.
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        async with async_session_maker() as session:
            stmt = (
                update(Meeting)
                .where(
                    (Meeting.scheduled_at - text("interval '3 hours'")) <= cutoff,
                    Meeting.completed_at.is_(None),
                )
                .values(completed_at=cutoff, survey_available_at=cutoff)
            )
            res = await session.execute(stmt)
            await session.commit()
            return res.rowcount or 0
