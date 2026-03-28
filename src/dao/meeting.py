from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, or_, select, insert, delete, update, text
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
    async def purge_older_than(cls, cutoff: datetime) -> int:
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        async with async_session_maker() as session:
            stmt = (
                update(Meeting)
                .where(
                    (Meeting.scheduled_at - text("interval '3 hours'")) <= cutoff,
                    Meeting.completed_at.is_(None),
                )
                .values(completed_at=cutoff)
            )
            res = await session.execute(stmt)
            await session.commit()
            return res.rowcount or 0

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
    async def get_unsynced(cls) -> list[Meeting]:
        async with async_session_maker() as session:
            query = select(Meeting).where(
                or_(
                    Meeting.synced_at.is_(None),
                    and_(
                        Meeting.updated_at.isnot(None),
                        Meeting.updated_at > Meeting.synced_at,
                    ),
                ),
            )
            result = await session.execute(query)
            return result.scalars().all()

    @classmethod
    async def mark_synced(
        cls, meeting_id: int, notion_page_id: str | None = None
    ) -> None:
        async with async_session_maker() as session:
            values: dict = {"synced_at": datetime.now(timezone.utc)}
            if notion_page_id:
                values["notion_page_id"] = notion_page_id
            await session.execute(
                update(Meeting).where(Meeting.id == meeting_id).values(**values)
            )
            await session.commit()

    @classmethod
    async def complete(
        cls,
        meeting_id: int,
        *,
        completed_at: datetime | None = None,
    ) -> tuple[Optional[Meeting], bool]:
        completed_at = completed_at or datetime.now(timezone.utc)
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)

        async with async_session_maker() as session:
            stmt = (
                update(Meeting)
                .where(Meeting.id == meeting_id, Meeting.completed_at.is_(None))
                .values(completed_at=completed_at)
                .returning(Meeting.id)
            )
            result = await session.execute(stmt)
            updated_id = result.scalar_one_or_none()
            await session.commit()

            if updated_id is None:
                # Either not found or already completed — fetch to distinguish
                query = (
                    select(Meeting)
                    .where(Meeting.id == meeting_id)
                    .options(
                        joinedload(Meeting.participants).selectinload(User.role_rel)
                    )
                )
                res = await session.execute(query)
                res = res.unique()
                meeting = res.scalar_one_or_none()
                return meeting, False

            # Reload with participants
            query = (
                select(Meeting)
                .where(Meeting.id == meeting_id)
                .options(joinedload(Meeting.participants).selectinload(User.role_rel))
            )
            res = await session.execute(query)
            res = res.unique()
            meeting = res.scalar_one_or_none()
            return meeting, True
