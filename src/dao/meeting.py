from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.meeting import CallStatus, Meeting, MeetingUser, ProposalStatus
from src.models.user import User


class MeetingDAO(BaseDAO):
    model = Meeting

    @staticmethod
    async def _reload_with_participants(
        session: AsyncSession, meeting_id: int
    ) -> Meeting | None:
        query = (
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .options(joinedload(Meeting.participants).selectinload(User.role_rel))
        )
        res = await session.execute(query)
        return res.unique().scalar_one_or_none()

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
        proposal_status: ProposalStatus = ProposalStatus.confirmed,
        proposed_by: int | None = None,
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
                    student_telegram_id=student_id,
                    mentee_telegram_tag=mentee_telegram_tag,
                    proposal_status=proposal_status,
                    proposed_by=proposed_by,
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

            return await cls._reload_with_participants(session, meeting.id)

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
            return await cls._reload_with_participants(session, meeting_id)

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

            return await cls._reload_with_participants(session, meeting_id)

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

            return await cls._reload_with_participants(session, meeting_id)

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

    @classmethod
    async def confirm_meeting(
        cls, meeting_id: int, confirming_user_id: int
    ) -> Optional[Meeting]:
        """Confirm a pending proposal. The confirming user must not be the proposer."""
        async with async_session_maker() as session:
            stmt = (
                update(Meeting)
                .where(
                    Meeting.id == meeting_id,
                    Meeting.proposed_by != confirming_user_id,
                    Meeting.proposal_status == ProposalStatus.pending_confirmation,
                )
                .values(proposal_status=ProposalStatus.confirmed)
                .returning(Meeting.id)
            )
            result = await session.execute(stmt)
            updated_id = result.scalar_one_or_none()
            await session.commit()

            if updated_id is None:
                return None

            return await cls._reload_with_participants(session, meeting_id)

    @classmethod
    async def decline_meeting(
        cls, meeting_id: int, declining_user_id: int
    ) -> Optional[int]:
        """Delete a pending meeting. Returns proposed_by for notification, or None."""
        async with async_session_maker() as session:
            subq = select(MeetingUser.meeting_id).where(
                MeetingUser.meeting_id == meeting_id,
                MeetingUser.user_id == declining_user_id,
            )
            stmt = (
                select(Meeting.proposed_by)
                .where(
                    Meeting.id == meeting_id,
                    Meeting.id.in_(subq),
                    Meeting.proposal_status == ProposalStatus.pending_confirmation,
                    Meeting.original_scheduled_at.is_(None),
                )
                .with_for_update()
            )
            result = await session.execute(stmt)
            proposed_by = result.scalar_one_or_none()
            if not proposed_by:
                return None

            await session.execute(delete(Meeting).where(Meeting.id == meeting_id))
            await session.commit()
            return proposed_by

    @classmethod
    async def propose_reschedule(
        cls,
        meeting_id: int,
        new_scheduled_at: datetime,
        new_link: str | None,
        proposer_id: int,
    ) -> Optional[Meeting]:
        """Save old scheduled_at → original_scheduled_at, update time and status."""
        async with async_session_maker() as session:
            subq = select(MeetingUser.meeting_id).where(
                MeetingUser.meeting_id == meeting_id,
                MeetingUser.user_id == proposer_id,
            )
            sel = (
                select(Meeting.scheduled_at)
                .where(
                    Meeting.id == meeting_id,
                    Meeting.id.in_(subq),
                    Meeting.proposal_status == ProposalStatus.confirmed,
                    Meeting.completed_at.is_(None),
                )
                .with_for_update()
            )
            old_scheduled = (await session.execute(sel)).scalar_one_or_none()
            if old_scheduled is None:
                return None

            values: dict = {
                "original_scheduled_at": old_scheduled,
                "scheduled_at": new_scheduled_at,
                "proposed_by": proposer_id,
                "proposal_status": ProposalStatus.pending_confirmation,
            }
            if new_link is not None:
                values["meeting_link"] = new_link

            stmt = (
                update(Meeting)
                .where(Meeting.id == meeting_id)
                .values(**values)
                .returning(Meeting.id)
            )
            await session.execute(stmt)
            await session.commit()

            return await cls._reload_with_participants(session, meeting_id)

    @classmethod
    async def confirm_reschedule(
        cls, meeting_id: int, confirming_user_id: int
    ) -> Optional[Meeting]:
        """Clear original_scheduled_at after reschedule is confirmed."""
        async with async_session_maker() as session:
            stmt = (
                update(Meeting)
                .where(
                    Meeting.id == meeting_id,
                    Meeting.proposed_by != confirming_user_id,
                    Meeting.original_scheduled_at.isnot(None),
                )
                .values(original_scheduled_at=None)
                .returning(Meeting.id)
            )
            result = await session.execute(stmt)
            updated_id = result.scalar_one_or_none()
            await session.commit()

            if updated_id is None:
                return None

            return await cls._reload_with_participants(session, meeting_id)

    @classmethod
    async def decline_reschedule(
        cls, meeting_id: int, declining_user_id: int
    ) -> Optional[Meeting]:
        """Revert scheduled_at ← original_scheduled_at and restore confirmed status."""
        async with async_session_maker() as session:
            subq = select(MeetingUser.meeting_id).where(
                MeetingUser.meeting_id == meeting_id,
                MeetingUser.user_id == declining_user_id,
            )
            sel = (
                select(Meeting.original_scheduled_at)
                .where(
                    Meeting.id == meeting_id,
                    Meeting.id.in_(subq),
                    Meeting.original_scheduled_at.isnot(None),
                    Meeting.proposal_status == ProposalStatus.pending_confirmation,
                )
                .with_for_update()
            )
            original = (await session.execute(sel)).scalar_one_or_none()
            if original is None:
                return None

            stmt = (
                update(Meeting)
                .where(Meeting.id == meeting_id)
                .values(
                    scheduled_at=original,
                    original_scheduled_at=None,
                    proposal_status=ProposalStatus.confirmed,
                )
                .returning(Meeting.id)
            )
            await session.execute(stmt)
            await session.commit()

            return await cls._reload_with_participants(session, meeting_id)

    @classmethod
    async def get_pending_for_user(cls, user_id: int) -> list[Meeting]:
        """Return pending meetings where the user is a participant."""
        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .join(MeetingUser, MeetingUser.meeting_id == Meeting.id)
                .where(
                    MeetingUser.user_id == user_id,
                    Meeting.proposal_status == ProposalStatus.pending_confirmation,
                )
                .options(joinedload(Meeting.participants).selectinload(User.role_rel))
                .order_by(Meeting.created_at.desc())
            )
            res = await session.execute(query)
            res = res.unique()
            return res.scalars().all()
