import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.dao import BaseDAO
from src.core.database import async_session_maker
from src.models.meeting import MeetingNotification, MeetingNotificationStatus

logger = logging.getLogger(__name__)


class MeetingNotificationDAO(BaseDAO):
    model = MeetingNotification

    @classmethod
    async def try_create(
        cls,
        meeting_id: int,
        user_id: int,
        notification_type: str,
        scheduled_window: datetime | None = None,
    ) -> tuple[MeetingNotification | None, bool]:
        """Attempt to insert a notification record. Returns (obj, created)."""
        async with async_session_maker() as session:
            stmt = (
                pg_insert(MeetingNotification)
                .values(
                    meeting_id=meeting_id,
                    user_id=user_id,
                    notification_type=notification_type,
                    scheduled_window=scheduled_window,
                    status=MeetingNotificationStatus.pending,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "meeting_id",
                        "user_id",
                        "notification_type",
                        "scheduled_window",
                    ]
                )
                .returning(MeetingNotification)
            )
            result = await session.execute(stmt)
            await session.commit()
            obj = result.scalar_one_or_none()
            if obj is not None:
                return obj, True

            existing = (
                await session.execute(
                    select(MeetingNotification).where(
                        MeetingNotification.meeting_id == meeting_id,
                        MeetingNotification.user_id == user_id,
                        MeetingNotification.notification_type == notification_type,
                        MeetingNotification.scheduled_window == scheduled_window,
                    )
                )
            ).scalar_one_or_none()
            return existing, False

    @classmethod
    async def mark_sent(cls, pk: int) -> None:
        await cls.update(
            pk,
            status=MeetingNotificationStatus.sent,
            sent_at=datetime.now(timezone.utc),
        )

    @classmethod
    async def mark_failed(cls, pk: int, error_message: str) -> None:
        await cls.update(
            pk,
            status=MeetingNotificationStatus.failed,
            sent_at=datetime.now(timezone.utc),
            error_message=error_message,
        )
