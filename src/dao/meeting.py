from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.meeting import CallStatus, Meeting, MeetingUser
from src.models.user import User


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
        student_id: int | None = None,
        topic: str | None = None,
        event_type: str | None = None,
        mentee_telegram_tag: str | None = None,
    ) -> Meeting:
        async with async_session_maker() as session:
            meeting_stmt = (
                insert(Meeting)
                .values(
                    description=description,
                    meeting_link=meeting_link,
                    scheduled_at=scheduled_at,
                    topic=topic or description,
                    event_type=event_type,
                    mentor_telegram_id=mentor_id,
                    mentee_telegram_tag=mentee_telegram_tag,
                )
                .returning(Meeting)
            )
            meeting_res = await session.execute(meeting_stmt)
            meeting: Meeting = meeting_res.scalar_one()

            participants = [{"meeting_id": meeting.id, "user_id": mentor_id}]
            if student_id is not None:
                participants.append({"meeting_id": meeting.id, "user_id": student_id})
            participants_stmt = insert(MeetingUser).values(participants)
            await session.execute(participants_stmt)
            await session.commit()

            # reload with participants
            query = (
                select(Meeting)
                .where(Meeting.id == meeting.id)
                .options(joinedload(Meeting.participants).selectinload(User.role_rel))
            )
            result = await session.execute(query)
            result = result.unique()
            return result.scalar_one()

    @classmethod
    async def get_for_user(
        cls, user_id: int, *, hide_past: bool = False
    ) -> list[Meeting]:
        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(MeetingUser.user_id == user_id)
                .options(joinedload(Meeting.participants).selectinload(User.role_rel))
                .order_by(Meeting.created_at.desc())
            )
            if hide_past:
                query = query.where(Meeting.completed_at.is_(None))
            res = await session.execute(query)
            res = res.unique()
            return res.scalars().all()

    @classmethod
    async def get_with_participants(cls, meeting_id: int) -> Optional[Meeting]:
        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .where(Meeting.id == meeting_id)
                .options(joinedload(Meeting.participants).selectinload(User.role_rel))
            )
            res = await session.execute(query)
            res = res.unique()
            return res.scalar_one_or_none()

    @classmethod
    async def delete_for_mentor(
        cls, meeting_id: int, mentor_id: int
    ) -> tuple[bool, str | None]:
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
                return False, None

            notion_page_id = meeting.notion_page_id
            await session.execute(delete(Meeting).where(Meeting.id == meeting_id))
            await session.commit()
            return True, notion_page_id

    @classmethod
    async def get_active_call_for_mentor(cls, mentor_id: int) -> Optional[Meeting]:
        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .where(
                    Meeting.mentor_telegram_id == mentor_id,
                    Meeting.call_status == CallStatus.ongoing,
                )
                .options(joinedload(Meeting.participants).selectinload(User.role_rel))
                .order_by(Meeting.scheduled_at.desc())
                .limit(1)
            )
            result = await session.execute(query)
            result = result.unique()
            return result.scalar_one_or_none()

    @classmethod
    async def start_call(cls, meeting_id: int, student_id: int) -> Optional[Meeting]:
        async with async_session_maker() as session:
            stmt = (
                update(Meeting)
                .where(
                    Meeting.id == meeting_id,
                    Meeting.call_status.is_(None),
                )
                .values(
                    call_status=CallStatus.ongoing,
                    student_telegram_id=student_id,
                )
                .returning(Meeting.id)
            )
            result = await session.execute(stmt)
            updated_id = result.scalar_one_or_none()
            await session.commit()

            if updated_id is None:
                return None

            query = (
                select(Meeting)
                .where(Meeting.id == meeting_id)
                .options(joinedload(Meeting.participants).selectinload(User.role_rel))
            )
            res = await session.execute(query)
            res = res.unique()
            return res.scalar_one_or_none()

    @classmethod
    async def finish_call(cls, meeting_id: int, mentor_id: int) -> Optional[Meeting]:
        async with async_session_maker() as session:
            now = datetime.now(timezone.utc)
            stmt = (
                update(Meeting)
                .where(
                    Meeting.id == meeting_id,
                    Meeting.mentor_telegram_id == mentor_id,
                    Meeting.call_status == CallStatus.ongoing,
                )
                .values(
                    call_status=CallStatus.finished,
                    completed_at=now,
                )
                .returning(Meeting.id)
            )
            result = await session.execute(stmt)
            updated_id = result.scalar_one_or_none()
            await session.commit()

            if updated_id is None:
                return None

            query = (
                select(Meeting)
                .where(Meeting.id == meeting_id)
                .options(joinedload(Meeting.participants).selectinload(User.role_rel))
            )
            res = await session.execute(query)
            res = res.unique()
            return res.scalar_one_or_none()

    @classmethod
    async def count_completed_for_pair(cls, mentor_id: int, student_id: int) -> int:
        async with async_session_maker() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Meeting)
                .where(
                    Meeting.mentor_telegram_id == mentor_id,
                    Meeting.student_telegram_id == student_id,
                    Meeting.completed_at.isnot(None),
                )
            )
            return result.scalar_one()
