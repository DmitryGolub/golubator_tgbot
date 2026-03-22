from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.models.meeting import Meeting, MeetingUser
from src.models.notion_cache import NotionCohortCache
from src.models.user import State, User
from src.services.notion import (
    NotionClient,
    NotionEventRepo,
    NotionMenteeRepo,
    NotionMentorRepo,
)

logger = logging.getLogger(__name__)

# State mapping: PostgreSQL enum ↔ Notion status name
_STATE_TO_NOTION: dict[State | None, str] = {
    State.greeting: "Greetings",
    State.study: "study",
    State.search: "Search",
    State.offer: "Offer",
    State.hold: "Lead",
}

_NOTION_TO_STATE: dict[str, State] = {
    "Greetings": State.greeting,
    "study": State.study,
    "Search": State.search,
    "Offer": State.offer,
    "Lead": State.hold,
    "Archive": State.hold,
}

# Notion meeting status mapping
_MEETING_STATUS_MAP: dict[str, str] = {
    "Запланирован": "scheduled",
    "Проведён": "completed",
    "Отменён": "cancelled",
}


def _make_session_factory() -> tuple:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


def _build_repos() -> tuple[
    NotionMentorRepo | None, NotionMenteeRepo | None, NotionEventRepo | None
]:
    token = settings.NOTION_TOKEN
    if not token:
        return None, None, None

    mentor_repo = None
    mentee_repo = None
    event_repo = None

    if settings.NOTION_MENTOR_DB_ID:
        mentor_repo = NotionMentorRepo(
            NotionClient(token, settings.NOTION_MENTOR_DB_ID)
        )

    mentee_db_id = settings.NOTION_MENTEE_DB_ID or settings.NOTION_DATABASE_ID
    if mentee_db_id:
        mentee_repo = NotionMenteeRepo(NotionClient(token, mentee_db_id))

    if settings.NOTION_EVENT_DB_ID:
        event_repo = NotionEventRepo(NotionClient(token, settings.NOTION_EVENT_DB_ID))

    return mentor_repo, mentee_repo, event_repo


async def _resolve_mentor_id(
    session: AsyncSession, mentor_name: str | None
) -> int | None:
    if not mentor_name:
        return None
    result = await session.execute(
        select(User.telegram_id).where(User.name == mentor_name)
    )
    return result.scalar_one_or_none()


async def _resolve_mentee_id(session: AsyncSession, tg_tag: str | None) -> int | None:
    if not tg_tag:
        return None
    clean = tg_tag.lstrip("@")
    result = await session.execute(
        select(User.telegram_id).where(User.username == clean)
    )
    return result.scalar_one_or_none()


async def _ensure_meeting_users(
    session: AsyncSession, meeting_id: int, mentor_id: int | None, mentee_id: int | None
) -> None:
    user_ids = [uid for uid in (mentor_id, mentee_id) if uid is not None]
    if not user_ids:
        return
    stmt = (
        pg_insert(MeetingUser)
        .values([{"meeting_id": meeting_id, "user_id": uid} for uid in user_ids])
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)


class NotionSyncServiceV2:
    """Bidirectional sync between PostgreSQL and Notion databases."""

    def __init__(
        self,
        mentor_repo: NotionMentorRepo | None,
        mentee_repo: NotionMenteeRepo | None,
        event_repo: NotionEventRepo | None,
    ):
        self.mentor_repo = mentor_repo
        self.mentee_repo = mentee_repo
        self.event_repo = event_repo

    # ── Automation webhook handlers (Notion → PostgreSQL) ───────────────

    async def handle_automation_user(self, payload: dict, source_db: str) -> None:
        """Handle Notion Automation webhook for user page.

        payload["data"] is a standard Notion page object with properties.
        """
        page = payload.get("data")
        if not page:
            logger.warning("Automation payload missing 'data' field")
            return

        page_id = page.get("id")
        if not page_id:
            return

        if source_db == "mentor" and self.mentor_repo:
            data = self.mentor_repo._parse_page(page)
            if not data.telegram_id:
                logger.debug("Skipping mentor page %s: no telegram_id", page_id)
                return
        elif source_db == "mentee" and self.mentee_repo:
            data = self.mentee_repo._parse_page(page)
            if not data.telegram_id:
                logger.debug("Skipping mentee page %s: no telegram_id", page_id)
                return
        else:
            return

        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                if source_db == "mentor":
                    await self._upsert_mentor(session, data, page_id)
                else:
                    await self._upsert_mentee(session, data, page_id)
                await session.commit()
        finally:
            await engine.dispose()

    async def handle_automation_event(self, payload: dict) -> None:
        """Handle Notion Automation webhook for event page."""
        page = payload.get("data")
        if not page:
            logger.warning("Automation payload missing 'data' field")
            return

        page_id = page.get("id")
        if not page_id or not self.event_repo:
            return

        data = self.event_repo._parse_page(page)

        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Meeting).where(Meeting.notion_page_id == page_id)
                )
                meeting = result.scalar_one_or_none()
                now = datetime.now(timezone.utc)

                mentor_id = await _resolve_mentor_id(session, data.mentor_name)
                mentee_id = await _resolve_mentee_id(session, data.mentee_tg_tag)

                if meeting:
                    if (
                        meeting.synced_at
                        and data.last_edited_time
                        and meeting.synced_at >= data.last_edited_time
                    ):
                        logger.debug("Skipping echo for event %s", page_id)
                        await _ensure_meeting_users(
                            session, meeting.id, mentor_id, mentee_id
                        )
                        await session.commit()
                        return

                    meeting.topic = data.topic
                    meeting.event_type = data.event_type
                    meeting.mentee_telegram_tag = data.mentee_tg_tag
                    meeting.recording_link = data.recording
                    meeting.summary = data.summary
                    meeting.action_items = data.action_items
                    meeting.project = data.project
                    if mentor_id:
                        meeting.mentor_telegram_id = mentor_id

                    if data.date:
                        from dateutil.parser import isoparse

                        try:
                            meeting.scheduled_at = isoparse(data.date)
                        except (ValueError, TypeError):
                            pass

                    if data.link:
                        meeting.meeting_link = data.link

                    if data.status == "Проведён" and not meeting.completed_at:
                        meeting.completed_at = now
                    elif data.status == "Отменён" and not meeting.completed_at:
                        meeting.completed_at = now

                    meeting.synced_at = now
                    await _ensure_meeting_users(
                        session, meeting.id, mentor_id, mentee_id
                    )
                else:
                    scheduled_at = None
                    if data.date:
                        from dateutil.parser import isoparse

                        try:
                            scheduled_at = isoparse(data.date)
                        except (ValueError, TypeError):
                            pass

                    new_meeting = Meeting(
                        notion_page_id=page_id,
                        topic=data.topic,
                        description=data.topic,
                        event_type=data.event_type,
                        scheduled_at=scheduled_at,
                        meeting_link=data.link,
                        mentee_telegram_tag=data.mentee_tg_tag,
                        recording_link=data.recording,
                        summary=data.summary,
                        action_items=data.action_items,
                        project=data.project,
                        synced_at=now,
                        mentor_telegram_id=mentor_id,
                    )
                    if data.status == "Проведён":
                        new_meeting.completed_at = now
                    session.add(new_meeting)
                    await session.flush()
                    await _ensure_meeting_users(
                        session, new_meeting.id, mentor_id, mentee_id
                    )

                await session.commit()
        finally:
            await engine.dispose()

    async def _upsert_mentor(self, session: AsyncSession, data, page_id: str) -> None:
        result = await session.execute(
            select(User).where(User.telegram_id == data.telegram_id)
        )
        user = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if user:
            # Anti-echo: skip if we just pushed this
            if (
                user.synced_at
                and data.last_edited_time
                and user.synced_at >= data.last_edited_time
            ):
                logger.debug("Skipping echo for mentor %s", data.telegram_id)
                return

            user.name = data.name or user.name
            user.notion_page_id = page_id
            user.notion_source_db = "mentor"
            user.synced_at = now
        else:
            session.add(
                User(
                    telegram_id=data.telegram_id,
                    username=data.name or str(data.telegram_id),
                    name=data.name or "",
                    notion_page_id=page_id,
                    notion_source_db="mentor",
                    synced_at=now,
                )
            )

    async def _upsert_mentee(self, session: AsyncSession, data, page_id: str) -> None:
        result = await session.execute(
            select(User).where(User.telegram_id == data.telegram_id)
        )
        user = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        resolved_mentor_id = await _resolve_mentor_id(
            session, getattr(data, "mentor_name", None)
        )

        if user:
            if (
                user.synced_at
                and data.last_edited_time
                and user.synced_at >= data.last_edited_time
            ):
                logger.debug("Skipping echo for mentee %s", data.telegram_id)
                return

            user.name = data.doc_name or user.name
            if data.status:
                user.state = _NOTION_TO_STATE.get(data.status, user.state)
            if resolved_mentor_id is not None:
                user.mentor_id = resolved_mentor_id
            user.notion_page_id = page_id
            user.notion_source_db = "mentee"
            user.synced_at = now
        else:
            state = _NOTION_TO_STATE.get(data.status) if data.status else State.greeting
            session.add(
                User(
                    telegram_id=data.telegram_id,
                    username=data.doc_name or str(data.telegram_id),
                    name=data.doc_name or "",
                    state=state,
                    mentor_id=resolved_mentor_id,
                    notion_page_id=page_id,
                    notion_source_db="mentee",
                    synced_at=now,
                )
            )

        # Update cohort cache (categories, tags, status)
        await self._sync_cohorts(session, data.telegram_id, data, now)

    async def _sync_cohorts(
        self,
        session: AsyncSession,
        telegram_id: int,
        data,
        now: datetime,
    ) -> None:
        from sqlalchemy import delete

        await session.execute(
            delete(NotionCohortCache).where(
                NotionCohortCache.user_telegram_id == telegram_id
            )
        )

        entries: list[tuple[str, str]] = []
        for cat in getattr(data, "categories", []):
            entries.append(("Category", cat))
        for tag in getattr(data, "tags", []):
            entries.append(("Tags", tag))
        if status := getattr(data, "status", None):
            entries.append(("Status", status))
        if intern := getattr(data, "intern", None):
            entries.append(("Стажор", intern))

        for cohort_type, cohort_value in entries:
            session.add(
                NotionCohortCache(
                    user_telegram_id=telegram_id,
                    cohort_type=cohort_type,
                    cohort_value=cohort_value,
                    synced_at=now,
                )
            )

    # ── Push: PostgreSQL → Notion ──────────────────────────────────────

    async def push_users(self) -> int:
        """Push unsynced user changes to Notion. Returns count of pushed records."""
        engine, factory = _make_session_factory()
        pushed = 0
        try:
            async with factory() as session:
                result = await session.execute(
                    select(User).where(
                        User.notion_page_id.isnot(None),
                        User.updated_at.isnot(None),
                        (User.synced_at.is_(None)) | (User.updated_at > User.synced_at),
                    )
                )
                users = result.scalars().all()

                now = datetime.now(timezone.utc)
                for user in users:
                    try:
                        if user.notion_source_db == "mentor" and self.mentor_repo:
                            props: dict = {}
                            if user.name:
                                props["Name"] = {
                                    "title": [{"text": {"content": user.name}}]
                                }
                            if props:
                                await self.mentor_repo.update_properties(
                                    user.notion_page_id, props
                                )
                        elif user.notion_source_db == "mentee" and self.mentee_repo:
                            props = {}
                            if user.name:
                                props["Doc name"] = {
                                    "title": [{"text": {"content": user.name}}]
                                }
                            notion_status = _STATE_TO_NOTION.get(user.state)
                            if notion_status:
                                props["Status"] = {"status": {"name": notion_status}}
                            if props:
                                await self.mentee_repo.update_properties(
                                    user.notion_page_id, props
                                )

                        await session.execute(
                            update(User)
                            .where(User.telegram_id == user.telegram_id)
                            .values(synced_at=now)
                        )
                        pushed += 1
                    except Exception as exc:
                        logger.error(
                            "Failed to push user %s to Notion: %s",
                            user.telegram_id,
                            exc,
                        )

                await session.commit()
        finally:
            await engine.dispose()

        if pushed:
            logger.info("Pushed %d users to Notion", pushed)
        return pushed

    async def push_events(self) -> int:
        """Push unsynced meeting changes to Notion. Returns count of pushed records."""
        if not self.event_repo:
            return 0

        engine, factory = _make_session_factory()
        pushed = 0
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Meeting).where(
                        (Meeting.synced_at.is_(None))
                        | (
                            Meeting.updated_at.isnot(None)
                            & (Meeting.updated_at > Meeting.synced_at)
                        ),
                    )
                )
                meetings = result.scalars().all()

                now = datetime.now(timezone.utc)
                for meeting in meetings:
                    try:
                        if meeting.notion_page_id is None:
                            # New meeting — create in Notion
                            page_id = await self.event_repo.create_event(
                                topic=meeting.topic or meeting.description or "Встреча",
                                date=(
                                    meeting.scheduled_at.isoformat()
                                    if meeting.scheduled_at
                                    else None
                                ),
                                event_type=meeting.event_type,
                                status=(
                                    "Проведён"
                                    if meeting.completed_at
                                    else "Запланирован"
                                ),
                                mentee_tg_tag=meeting.mentee_telegram_tag,
                                link=meeting.meeting_link,
                            )
                            if page_id:
                                meeting.notion_page_id = page_id
                                meeting.synced_at = now
                        else:
                            # Existing — update properties
                            props: dict = {}
                            if meeting.topic:
                                props["Тема"] = {
                                    "title": [{"text": {"content": meeting.topic}}]
                                }
                            if meeting.completed_at:
                                props["Статус"] = {"status": {"name": "Проведён"}}
                            if meeting.summary:
                                props["Итоги"] = {
                                    "rich_text": [
                                        {"text": {"content": meeting.summary}}
                                    ]
                                }
                            if meeting.action_items:
                                props["Action items"] = {
                                    "rich_text": [
                                        {"text": {"content": meeting.action_items}}
                                    ]
                                }
                            if props:
                                await self.event_repo.update_properties(
                                    meeting.notion_page_id, props
                                )
                            meeting.synced_at = now

                        pushed += 1
                    except Exception as exc:
                        logger.error(
                            "Failed to push meeting %s to Notion: %s",
                            meeting.id,
                            exc,
                        )

                await session.commit()
        finally:
            await engine.dispose()

        if pushed:
            logger.info("Pushed %d events to Notion", pushed)
        return pushed

    # ── Backup pull (full sync, fallback for missed webhooks) ──────────

    async def backup_pull_users(self) -> int:
        """Full pull of all users from both Notion databases."""
        count = 0
        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                if self.mentor_repo:
                    mentors = await self.mentor_repo.get_all()
                    for m in mentors:
                        if m.telegram_id:
                            await self._upsert_mentor(session, m, m.page_id)
                            count += 1

                if self.mentee_repo:
                    mentees = await self.mentee_repo.get_all()
                    for m in mentees:
                        if m.telegram_id:
                            await self._upsert_mentee(session, m, m.page_id)
                            count += 1

                await session.commit()
        finally:
            await engine.dispose()

        logger.info("Backup pull: %d users synced", count)
        return count

    async def backup_pull_events(self) -> int:
        """Full pull of events from Notion."""
        if not self.event_repo:
            return 0

        events = await self.event_repo.get_all()
        count = 0
        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                for ev in events:
                    try:
                        result = await session.execute(
                            select(Meeting).where(Meeting.notion_page_id == ev.page_id)
                        )
                        meeting = result.scalar_one_or_none()

                        now = datetime.now(timezone.utc)
                        mentor_id = await _resolve_mentor_id(session, ev.mentor_name)
                        mentee_id = await _resolve_mentee_id(session, ev.mentee_tg_tag)

                        if meeting:
                            if (
                                meeting.synced_at
                                and ev.last_edited_time
                                and meeting.synced_at >= ev.last_edited_time
                            ):
                                await _ensure_meeting_users(
                                    session, meeting.id, mentor_id, mentee_id
                                )
                                continue
                            meeting.topic = ev.topic
                            meeting.event_type = ev.event_type
                            meeting.mentee_telegram_tag = ev.mentee_tg_tag
                            meeting.recording_link = ev.recording
                            meeting.summary = ev.summary
                            meeting.action_items = ev.action_items
                            meeting.project = ev.project
                            if mentor_id:
                                meeting.mentor_telegram_id = mentor_id
                            if ev.link:
                                meeting.meeting_link = ev.link
                            if ev.status == "Проведён" and not meeting.completed_at:
                                meeting.completed_at = now
                            meeting.synced_at = now
                            await _ensure_meeting_users(
                                session, meeting.id, mentor_id, mentee_id
                            )
                        else:
                            scheduled_at = None
                            if ev.date:
                                from dateutil.parser import isoparse

                                try:
                                    scheduled_at = isoparse(ev.date)
                                except (ValueError, TypeError):
                                    pass

                            new_meeting = Meeting(
                                notion_page_id=ev.page_id,
                                topic=ev.topic,
                                description=ev.topic,
                                event_type=ev.event_type,
                                scheduled_at=scheduled_at,
                                meeting_link=ev.link,
                                mentee_telegram_tag=ev.mentee_tg_tag,
                                recording_link=ev.recording,
                                summary=ev.summary,
                                action_items=ev.action_items,
                                project=ev.project,
                                synced_at=now,
                                mentor_telegram_id=mentor_id,
                            )
                            if ev.status == "Проведён":
                                new_meeting.completed_at = now
                            session.add(new_meeting)
                            await session.flush()
                            await _ensure_meeting_users(
                                session, new_meeting.id, mentor_id, mentee_id
                            )

                        count += 1
                    except Exception as exc:
                        logger.error("Error syncing event %s: %s", ev.page_id, exc)

                await session.commit()
        finally:
            await engine.dispose()

        logger.info("Backup pull: %d events synced", count)
        return count


_sync_service: NotionSyncServiceV2 | None = None


def get_sync_service() -> NotionSyncServiceV2 | None:
    global _sync_service
    if _sync_service is None:
        mentor_repo, mentee_repo, event_repo = _build_repos()
        if not any((mentor_repo, mentee_repo, event_repo)):
            return None
        _sync_service = NotionSyncServiceV2(mentor_repo, mentee_repo, event_repo)
    return _sync_service
