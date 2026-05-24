from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.models.meeting import Meeting, MeetingUser
from src.models.mentee import Mentee
from src.models.mentor import Mentor
from src.models.cohort import Cohort, UserCohort
from src.models.user import User
from src.models.trigger import TriggerType
from src.services.notion import (
    NotionClient,
    NotionEventRepo,
    NotionMenteeRepo,
    NotionMentorRepo,
    NotionPageArchivedError,
)

logger = logging.getLogger(__name__)

# Mapping from Notion Role select → DB role name
_NOTION_ROLE_MAP: dict[str, str] = {
    "mentor": "mentor",
    "admin": "admin",
    "админ": "admin",
    "ментор": "mentor",
    "direction_lead": "direction_lead",
    "job_search_lead": "job_search_lead",
    "education_lead": "education_lead",
}

_DB_ROLE_TO_NOTION: dict[str, str] = {
    "mentor": "mentor",
    "admin": "admin",
    "direction_lead": "direction_lead",
    "job_search_lead": "job_search_lead",
    "education_lead": "education_lead",
}


def _resolve_role_name(notion_role: str | None) -> str:
    if notion_role is None:
        return "mentor"
    return _NOTION_ROLE_MAP.get(notion_role.strip().lower(), "mentor")


def _clean_name(name: str | None) -> str | None:
    if not name:
        return None
    return name.lstrip("@").strip() or None


def _make_session_factory() -> tuple:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    from dateutil.parser import isoparse

    try:
        return isoparse(value)
    except (ValueError, TypeError):
        return None


def _same_moment(a: datetime | None, b: datetime | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return a.astimezone(timezone.utc) == b.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return a == b


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


async def _ensure_user_exists(
    session: AsyncSession,
    telegram_id: int | None,
    name: str | None = None,
    role_name: str = "student",
    current_placeholder_id: int | None = None,
) -> int:
    """Ensure a User record exists, creating a placeholder if telegram_id is None.

    Returns the telegram_id (real or placeholder) of the User.
    """
    from src.models.role import RoleModel

    clean = _clean_name(name)

    if telegram_id is not None:
        # Real telegram_id provided
        if current_placeholder_id is not None and current_placeholder_id < 0:
            # Mentor/Mentee already has a placeholder User — merge
            existing_real = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            real_user = existing_real.scalar_one_or_none()

            if not real_user:
                # No real user yet — update placeholder PK (CASCADE updates all FKs)
                try:
                    async with session.begin_nested():
                        result = await session.execute(
                            update(User)
                            .where(User.telegram_id == current_placeholder_id)
                            .values(telegram_id=telegram_id)
                            .returning(User.telegram_id)
                        )
                        await session.flush()
                        if result.scalar_one_or_none() is None:
                            # Another webhook already performed the merge — skip
                            logger.debug(
                                "Placeholder merge skipped (already merged): %s -> %s",
                                current_placeholder_id,
                                telegram_id,
                            )
                except IntegrityError:
                    # Savepoint rolled back automatically; outer transaction intact
                    logger.warning(
                        "IntegrityError during placeholder merge %s -> %s",
                        current_placeholder_id,
                        telegram_id,
                    )
                    # Check if a real user now exists (concurrent /start)
                    real_result = await session.execute(
                        select(User).where(User.telegram_id == telegram_id)
                    )
                    real_user = real_result.scalar_one_or_none()
                    if real_user:
                        ph = await session.execute(
                            select(User).where(
                                User.telegram_id == current_placeholder_id
                            )
                        )
                        ph_user = ph.scalar_one_or_none()
                        if ph_user:
                            await session.delete(ph_user)
                            await session.flush()
                        return telegram_id
                    raise RuntimeError(
                        f"Inconsistent state: merge {current_placeholder_id} -> "
                        f"{telegram_id} failed but no real user found"
                    )
            else:
                # Real user already exists — delete placeholder
                placeholder = await session.execute(
                    select(User).where(User.telegram_id == current_placeholder_id)
                )
                ph_user = placeholder.scalar_one_or_none()
                if ph_user:
                    await session.delete(ph_user)
                    await session.flush()
                # Update role if needed
                if role_name != "student" or real_user.role_id is None:
                    role_result = await session.execute(
                        select(RoleModel.id).where(RoleModel.name == role_name)
                    )
                    role_id = role_result.scalar_one_or_none()
                    if role_id and real_user.role_id != role_id:
                        real_user.role_id = role_id
        else:
            # No placeholder — normal upsert
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                role_result = await session.execute(
                    select(RoleModel.id).where(RoleModel.name == role_name)
                )
                role_id = role_result.scalar_one_or_none()
                session.add(
                    User(
                        telegram_id=telegram_id,
                        name=clean or str(telegram_id),
                        role_id=role_id,
                        registered_at=None,
                    )
                )
                await session.flush()
            else:
                if role_name != "student" or user.role_id is None:
                    role_result = await session.execute(
                        select(RoleModel.id).where(RoleModel.name == role_name)
                    )
                    role_id = role_result.scalar_one_or_none()
                    if role_id and user.role_id != role_id:
                        user.role_id = role_id

        return telegram_id

    # telegram_id is None — need a placeholder
    if current_placeholder_id is not None and current_placeholder_id < 0:
        if clean:
            result = await session.execute(
                select(User).where(User.telegram_id == current_placeholder_id)
            )
            ph_user = result.scalar_one_or_none()
            if ph_user and ph_user.name != clean:
                logger.debug(
                    "Updated placeholder user %s name: %r -> %r",
                    current_placeholder_id,
                    ph_user.name,
                    clean,
                )
                ph_user.name = clean
        return current_placeholder_id

    # Create new placeholder
    from sqlalchemy import text as sa_text

    seq_result = await session.execute(
        sa_text("SELECT nextval('iam.placeholder_user_seq')")
    )
    placeholder_id = seq_result.scalar()
    role_result = await session.execute(
        select(RoleModel.id).where(RoleModel.name == role_name)
    )
    role_id = role_result.scalar_one_or_none()
    session.add(
        User(
            telegram_id=placeholder_id,
            name=clean or "Placeholder",
            role_id=role_id,
            registered_at=None,
        )
    )
    await session.flush()
    return placeholder_id


def _safe_scalar_one_or_none(result, label: str, value: str):
    rows = result.scalars().all()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning("Multiple results for %s='%s', using first", label, value)
    return rows[0]


async def _resolve_mentor_id(
    session: AsyncSession, mentor_name: str | None, mentor_email: str | None = None
) -> int | None:
    if not mentor_name and not mentor_email:
        return None
    if mentor_email:
        result = await session.execute(
            select(Mentor.id).where(Mentor.email == mentor_email)
        )
        mid = _safe_scalar_one_or_none(result, "mentor.email", mentor_email)
        if mid:
            return mid
    if mentor_name:
        clean = _clean_name(mentor_name)
        if clean:
            result = await session.execute(
                select(Mentor.id).where(func.ltrim(Mentor.name, "@") == clean)
            )
            mid = _safe_scalar_one_or_none(result, "mentor.name", clean)
            if mid:
                return mid
    return None


async def _resolve_mentor_telegram_id(
    session: AsyncSession, mentor_name: str | None, mentor_email: str | None = None
) -> int | None:
    if not mentor_name and not mentor_email:
        return None
    if mentor_email:
        result = await session.execute(
            select(Mentor.telegram_id).where(Mentor.email == mentor_email)
        )
        tid = _safe_scalar_one_or_none(result, "mentor.email", mentor_email)
        if tid:
            return tid
    if mentor_name:
        clean = _clean_name(mentor_name)
        if clean:
            result = await session.execute(
                select(Mentor.telegram_id).where(func.ltrim(Mentor.name, "@") == clean)
            )
            tid = _safe_scalar_one_or_none(result, "mentor.name", clean)
            if tid:
                return tid
    return None


async def _resolve_mentee_id(session: AsyncSession, tg_tag: str | None) -> int | None:
    if not tg_tag:
        return None
    clean = tg_tag.lstrip("@")
    result = await session.execute(
        select(User.telegram_id).where(User.username == clean)
    )
    tid = _safe_scalar_one_or_none(result, "user.username", clean)
    if tid is not None:
        return tid
    # Fallback: look up by doc_name in mentees (covers unregistered students)
    for pattern in (f"@{clean}", clean):
        result = await session.execute(
            select(Mentee.telegram_id).where(Mentee.doc_name == pattern)
        )
        tid = _safe_scalar_one_or_none(result, "mentee.doc_name", pattern)
        if tid is not None:
            return tid
    return None


async def _resolve_mentee_ids(session: AsyncSession, tg_tag: str | None) -> list[int]:
    if not tg_tag:
        return []
    ids: list[int] = []
    for tag in tg_tag.split(","):
        tag = tag.strip()
        if not tag:
            continue
        tid = await _resolve_mentee_id(session, tag)
        if tid is not None:
            ids.append(tid)
    return ids


async def _ensure_meeting_users(
    session: AsyncSession,
    meeting_id: int,
    user_ids: list[int] | None = None,
    # backward compat params
    mentor_id: int | None = None,
    mentee_id: int | None = None,
) -> None:
    if user_ids is None:
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
        page = payload.get("data")
        if not page:
            logger.warning("Automation payload missing 'data' field")
            return

        page_id = page.get("id")
        if not page_id:
            return

        if source_db == "mentor" and self.mentor_repo:
            data = self.mentor_repo._parse_page(page)
        elif source_db == "mentee" and self.mentee_repo:
            data = self.mentee_repo._parse_page(page)
        else:
            return

        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                events: list[tuple[TriggerType, dict]] = []
                if source_db == "mentor":
                    await self._upsert_mentor(session, data, page_id)
                else:
                    events = await self._upsert_mentee(session, data, page_id)
                await session.commit()

                if events:
                    from src.services.events.dispatcher import EventDispatcher

                    for trigger_type, ctx in events:
                        await EventDispatcher.emit(trigger_type, ctx)
        finally:
            await engine.dispose()

    async def handle_automation_event(self, payload: dict) -> None:
        page = payload.get("data")
        if not page:
            logger.warning("Automation payload missing 'data' field")
            return

        page_id = page.get("id")
        if not page_id or not self.event_repo:
            return

        data = self.event_repo._parse_page(page)

        reschedule_target: tuple[int, datetime] | None = None

        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Meeting).where(Meeting.notion_page_id == page_id)
                )
                meeting = result.scalar_one_or_none()
                now = datetime.now(timezone.utc)

                mentor_tid = await _resolve_mentor_telegram_id(
                    session, data.mentor_name
                )
                mentee_tids = await _resolve_mentee_ids(session, data.mentee_tg_tag)
                all_user_ids = ([mentor_tid] if mentor_tid else []) + mentee_tids

                if meeting:
                    if (
                        meeting.synced_at
                        and data.last_edited_time
                        and meeting.synced_at >= data.last_edited_time
                    ):
                        logger.debug("Skipping echo for event %s", page_id)
                        await _ensure_meeting_users(
                            session, meeting.id, user_ids=all_user_ids
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
                    if mentor_tid:
                        meeting.mentor_telegram_id = mentor_tid

                    new_scheduled_at = _parse_iso_date(data.date)
                    if (
                        new_scheduled_at is not None
                        and not meeting.is_cancelled
                        and not _same_moment(meeting.scheduled_at, new_scheduled_at)
                    ):
                        reschedule_target = (meeting.id, new_scheduled_at)

                    if data.link:
                        meeting.meeting_link = data.link

                    if (
                        data.status in ("Проведён", "Отменён")
                        and not meeting.completed_at
                    ):
                        meeting.completed_at = now
                    if data.status == "Отменён":
                        meeting.is_cancelled = True
                    elif data.status == "Проведён":
                        meeting.is_cancelled = False

                    meeting.synced_at = now
                    await _ensure_meeting_users(
                        session, meeting.id, user_ids=all_user_ids
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
                        mentor_telegram_id=mentor_tid,
                    )
                    if data.status in ("Проведён", "Отменён"):
                        new_meeting.completed_at = now
                    if data.status == "Отменён":
                        new_meeting.is_cancelled = True
                    session.add(new_meeting)
                    await session.flush()
                    await _ensure_meeting_users(
                        session, new_meeting.id, user_ids=all_user_ids
                    )
                    # Set confirmation state for Notion-created meetings
                    clean_user_ids = [uid for uid in all_user_ids if uid is not None]
                    if clean_user_ids:
                        from src.dao.meeting import MeetingDAO
                        proposer_id = mentor_tid or next(
                            (uid for uid in clean_user_ids if uid > 0),
                            clean_user_ids[0],
                        )
                        await MeetingDAO.setup_confirmation_state(
                            session,
                            new_meeting.id,
                            set(clean_user_ids),
                            proposer_id,
                        )

                await session.commit()
        finally:
            await engine.dispose()

        if reschedule_target is not None:
            meeting_id, new_dt = reschedule_target
            await self._apply_notion_reschedule(meeting_id, new_dt)

    async def _apply_notion_reschedule(
        self, meeting_id: int, new_scheduled_at: datetime
    ) -> None:
        from src.dao.meeting import MeetingDAO

        """Dispatch a Notion-originating scheduled_at change through the DAO.

        Past moves bypass confirmation silently. Future moves reuse
        `propose_reschedule`; when the DAO auto-confirms (no real participant
        left to confirm), the proposer gets an FYI; otherwise the real
        participants receive a standard pending-proposal message.
        """
        from src.utils.time import is_past

        existing = await MeetingDAO.get_with_participants(meeting_id)
        if existing is None or existing.is_cancelled:
            return

        proposer_id: int | None = None
        participant_ids = [p.telegram_id for p in existing.participants or []]
        if (
            existing.mentor_telegram_id is not None
            and existing.mentor_telegram_id in participant_ids
        ):
            proposer_id = existing.mentor_telegram_id
        else:
            proposer_id = next(
                (pid for pid in participant_ids if pid > 0),
                next(iter(participant_ids), None),
            )

        if proposer_id is None:
            logger.info(
                "notion.reschedule: no participants on meeting %s, skipping",
                meeting_id,
            )
            return

        if is_past(new_scheduled_at):
            await MeetingDAO.silent_reschedule_past(
                meeting_id=meeting_id,
                new_scheduled_at=new_scheduled_at,
                proposer_id=proposer_id,
            )
            logger.info(
                "notion.reschedule: past move applied silently",
                extra={"meeting_id": meeting_id},
            )
            return

        meeting = await MeetingDAO.propose_reschedule(
            meeting_id=meeting_id,
            new_scheduled_at=new_scheduled_at,
            new_link=None,
            proposer_id=proposer_id,
        )
        if meeting is None:
            return

        from src.dao.user import UserDAO
        from src.models.meeting import ProposalStatus
        from src.services.meeting.proposal_text import format_when
        from src.tasks._db import get_worker_bot
        from src.tasks.meeting import _send_confirmation_request
        from src.utils.escape import e as _escape

        proposer = await UserDAO.find_one_or_none(telegram_id=proposer_id)

        bot = get_worker_bot()
        when_str = format_when(meeting.scheduled_at)
        auto_confirmed = meeting.proposal_status == ProposalStatus.confirmed
        other_names: list[str] = []
        for participant in meeting.participants or []:
            if participant.telegram_id == proposer_id:
                continue
            other_names.append(
                participant.name if participant.name else f"id{participant.telegram_id}"
            )
            if auto_confirmed:
                continue
            await _send_confirmation_request(
                meeting.id, participant.telegram_id, bot=bot
            )

        if proposer is not None and proposer_id > 0:
            other_label = ", ".join(other_names) if other_names else "участника"
            if auto_confirmed:
                proposer_text = (
                    f"✅ Встреча с <b>{_escape(other_label)}</b> перенесена на "
                    f"{when_str}. Подтверждение не требуется."
                )
            else:
                proposer_text = (
                    f"✅ Перенос встречи на {when_str} предложен. "
                    f"Ждём подтверждения от <b>{_escape(other_label)}</b>."
                )
            await bot.send_message(proposer.telegram_id, proposer_text)

    async def _upsert_mentor(self, session: AsyncSession, data, page_id: str) -> None:
        result = await session.execute(
            select(Mentor).where(Mentor.notion_page_id == page_id)
        )
        mentor = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        role_name = _resolve_role_name(getattr(data, "role", None))

        if mentor:
            if (
                mentor.synced_at
                and data.last_edited_time
                and mentor.synced_at >= data.last_edited_time
            ):
                logger.debug("Skipping echo for mentor page %s", page_id)
                return

            mentor.name = _clean_name(data.name) or mentor.name
            mentor.email = getattr(data, "email", None) or mentor.email
            mentor.about = getattr(data, "about", None) or mentor.about
            mentor.membership_type = (
                getattr(data, "membership_type", None) or mentor.membership_type
            )
            channel_id = getattr(data, "channel_id", None)
            if channel_id is not None:
                mentor.channel_id = channel_id
            if mentor.notion_archived:
                mentor.notion_archived = False
            mentor.synced_at = now

            current_ph = (
                mentor.telegram_id
                if mentor.telegram_id is not None and mentor.telegram_id < 0
                else None
            )
            user_tid = await _ensure_user_exists(
                session,
                telegram_id=data.telegram_id,
                name=data.name,
                role_name=role_name,
                current_placeholder_id=current_ph,
            )
            mentor.telegram_id = user_tid
        else:
            new_mentor = Mentor(
                notion_page_id=page_id,
                name=_clean_name(data.name),
                email=getattr(data, "email", None),
                about=getattr(data, "about", None),
                membership_type=getattr(data, "membership_type", None),
                channel_id=getattr(data, "channel_id", None),
                synced_at=now,
            )
            session.add(new_mentor)
            await session.flush()

            user_tid = await _ensure_user_exists(
                session,
                telegram_id=data.telegram_id,
                name=data.name,
                role_name=role_name,
            )
            new_mentor.telegram_id = user_tid

    async def _upsert_mentee(
        self, session: AsyncSession, data, page_id: str
    ) -> list[tuple[TriggerType, dict]]:
        result = await session.execute(
            select(Mentee).where(Mentee.notion_page_id == page_id)
        )
        mentee = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        resolved_mentor_id = await _resolve_mentor_id(
            session,
            getattr(data, "mentor_name", None),
            getattr(data, "mentor_email", None),
        )

        new_mentee: Mentee | None = None
        contract_signed_emit = False
        if mentee:
            # Always try to fill missing mentor_id (handles out-of-order sync)
            if resolved_mentor_id is not None and mentee.mentor_id is None:
                mentee.mentor_id = resolved_mentor_id

            if (
                mentee.synced_at
                and data.last_edited_time
                and mentee.synced_at >= data.last_edited_time
            ):
                logger.debug("Skipping echo for mentee page %s", page_id)
                return []

            mentee.doc_name = data.doc_name or mentee.doc_name
            if resolved_mentor_id is not None:
                mentee.mentor_id = resolved_mentor_id
            elif resolved_mentor_id is None and getattr(data, "mentor_name", None):
                logger.warning(
                    "Mentor '%s' not found in DB for mentee page %s",
                    data.mentor_name,
                    page_id,
                )
            old_contract = bool(mentee.contract)
            mentee.contract = getattr(data, "contract", mentee.contract)
            if (
                not old_contract
                and bool(mentee.contract)
                and mentee.telegram_id is not None
                and mentee.telegram_id > 0
            ):
                contract_signed_emit = True
            mentee.intern = getattr(data, "intern", mentee.intern)
            mentee.contract_version = getattr(
                data, "contract_version", mentee.contract_version
            )
            mentee.contract_expires = getattr(
                data, "contract_expires", mentee.contract_expires
            )
            mentee.student_score = getattr(data, "student_score", mentee.student_score)
            if mentee.notion_archived:
                mentee.notion_archived = False
            mentee.synced_at = now

            current_ph = (
                mentee.telegram_id
                if mentee.telegram_id is not None and mentee.telegram_id < 0
                else None
            )
            user_tid = await _ensure_user_exists(
                session,
                telegram_id=data.telegram_id,
                name=data.doc_name,
                role_name="student",
                current_placeholder_id=current_ph,
            )
            if user_tid != mentee.telegram_id:
                conflict = await session.execute(
                    select(Mentee.id).where(
                        Mentee.telegram_id == user_tid,
                        Mentee.id != mentee.id,
                    )
                )
                if conflict.scalar_one_or_none() is not None:
                    logger.warning(
                        "telegram_id %s already belongs to another mentee, "
                        "skipping assignment for mentee id=%s (page %s)",
                        user_tid,
                        mentee.id,
                        page_id,
                    )
                else:
                    mentee.telegram_id = user_tid
        else:
            new_mentee = Mentee(
                notion_page_id=page_id,
                doc_name=data.doc_name,
                mentor_id=resolved_mentor_id,
                contract=getattr(data, "contract", False),
                intern=getattr(data, "intern", None),
                contract_version=getattr(data, "contract_version", None),
                contract_expires=getattr(data, "contract_expires", None),
                student_score=getattr(data, "student_score", None),
                synced_at=now,
            )
            session.add(new_mentee)
            await session.flush()

            user_tid = await _ensure_user_exists(
                session,
                telegram_id=data.telegram_id,
                name=data.doc_name,
                role_name="student",
            )
            conflict = await session.execute(
                select(Mentee.id).where(
                    Mentee.telegram_id == user_tid,
                    Mentee.id != new_mentee.id,
                )
            )
            if conflict.scalar_one_or_none() is not None:
                logger.warning(
                    "telegram_id %s already belongs to another mentee, "
                    "skipping assignment for new mentee id=%s (page %s)",
                    user_tid,
                    new_mentee.id,
                    page_id,
                )
            else:
                new_mentee.telegram_id = user_tid

        mentee_record = mentee or new_mentee
        if mentee_record.telegram_id is None:
            logger.warning(
                "Mentee id=%s (page %s) has no telegram_id, skipping cohort sync",
                mentee_record.id,
                page_id,
            )
            return []
        cohort_diffs = await self._sync_cohorts(
            session,
            mentee_record.telegram_id,
            data,
            now,
            page_created_time=getattr(data, "created_time", None),
        )
        events: list[tuple[TriggerType, dict]] = [
            (TriggerType.cohort_changed, d) for d in cohort_diffs
        ]
        if contract_signed_emit:
            events.append(
                (
                    TriggerType.contract_signed,
                    {"user_telegram_id": mentee_record.telegram_id},
                )
            )
        return events

    async def _sync_cohorts(
        self,
        session: AsyncSession,
        user_telegram_id: int,
        data,
        now: datetime,
        page_created_time: datetime | None = None,
        old_ids_by_entry: dict[tuple[str, str], int] | None = None,
    ) -> list[dict]:
        """Sync cohorts and return list of diffs for changed cohorts.

        If ``old_ids_by_entry`` is provided, the caller has already prefetched
        the current UserCohort snapshot in a batch and we skip the per-user
        SELECT. The dict is not mutated.
        """
        from sqlalchemy import delete, tuple_

        # Build desired state from payload first — no SQL yet.
        new_map: dict[str, set[str]] = defaultdict(set)
        for cat in getattr(data, "categories", []):
            new_map["Category"].add(cat)
        for tag in getattr(data, "tags", []):
            new_map["Tags"].add(tag)
        if status := getattr(data, "status", None):
            new_map["Status"].add(status)
        if intern := getattr(data, "intern", None):
            new_map["Стажор"].add(intern)

        # Snapshot current cohorts (with ids so we can delete only removed ones).
        old_map: dict[str, set[str]] = defaultdict(set)
        if old_ids_by_entry is None:
            old_ids_by_entry = {}
            old_result = await session.execute(
                select(Cohort.id, Cohort.type, Cohort.value)
                .join(UserCohort, UserCohort.cohort_id == Cohort.id)
                .where(UserCohort.user_telegram_id == user_telegram_id)
            )
            for cid, ctype, cvalue in old_result.all():
                old_map[ctype].add(cvalue)
                old_ids_by_entry[(ctype, cvalue)] = cid
        else:
            for ctype, cvalue in old_ids_by_entry:
                old_map[ctype].add(cvalue)

        # Short-circuit: nothing to write if desired state matches current state.
        if old_map == new_map:
            return []

        new_entries: set[tuple[str, str]] = {
            (ct, v) for ct, values in new_map.items() for v in values
        }
        old_entries: set[tuple[str, str]] = set(old_ids_by_entry)
        added_entries = new_entries - old_entries
        removed_entries = old_entries - new_entries

        # Bulk upsert Cohort rows for all entries we still want (cheap no-op if
        # they already exist). Batches all categories in a single round-trip.
        if new_entries:
            await session.execute(
                pg_insert(Cohort)
                .values([{"type": ct, "value": v} for ct, v in new_entries])
                .on_conflict_do_nothing(constraint="uq_cohort_type_value")
            )

        # Batch-resolve Cohort.id for every added entry in one query.
        added_ids: list[int] = []
        if added_entries:
            id_result = await session.execute(
                select(Cohort.id, Cohort.type, Cohort.value).where(
                    tuple_(Cohort.type, Cohort.value).in_(added_entries)
                )
            )
            for cid, ct, v in id_result.all():
                if (ct, v) in added_entries:
                    added_ids.append(cid)

        # Point-delete UserCohort rows that dropped out.
        if removed_entries:
            removed_ids = [old_ids_by_entry[e] for e in removed_entries]
            await session.execute(
                delete(UserCohort).where(
                    UserCohort.user_telegram_id == user_telegram_id,
                    UserCohort.cohort_id.in_(removed_ids),
                )
            )

        # Insert only the new links.
        for cohort_id in added_ids:
            session.add(
                UserCohort(
                    user_telegram_id=user_telegram_id,
                    cohort_id=cohort_id,
                    synced_at=now,
                )
            )

        diffs: list[dict] = []
        all_types = set(old_map) | set(new_map)
        for ct in all_types:
            old_vals = old_map.get(ct, set())
            new_vals = new_map.get(ct, set())
            if old_vals == new_vals:
                continue
            for added in new_vals - old_vals:
                old_single = next(iter(old_vals), None) if len(old_vals) == 1 else None
                diffs.append(
                    {
                        "user_telegram_id": user_telegram_id,
                        "cohort_type": ct,
                        "old_value": old_single,
                        "new_value": added,
                    }
                )
            for removed in old_vals - new_vals:
                diffs.append(
                    {
                        "user_telegram_id": user_telegram_id,
                        "cohort_type": ct,
                        "old_value": removed,
                        "new_value": None,
                    }
                )

        from src.models.stage_transition import StageTransition

        for diff in diffs:
            if diff["new_value"] is None:
                continue
            transition_kwargs = dict(
                user_telegram_id=diff["user_telegram_id"],
                cohort_type=diff["cohort_type"],
                old_value=diff["old_value"],
                new_value=diff["new_value"],
                source="notion_sync",
            )
            if diff["old_value"] is None and page_created_time is not None:
                transition_kwargs["created_at"] = page_created_time
            session.add(StageTransition(**transition_kwargs))

        return diffs

    # ── Cohort sync (standalone stream) ─────────────────────────────────

    async def handle_automation_cohort(self, payload: dict) -> None:
        page = payload.get("data")
        if not page:
            logger.warning("Automation payload missing 'data' field")
            return

        page_id = page.get("id")
        if not page_id or not self.mentee_repo:
            return

        data = self.mentee_repo._parse_page(page)

        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Mentee).where(Mentee.notion_page_id == page_id)
                )
                mentee = result.scalar_one_or_none()
                if not mentee:
                    logger.warning(
                        "Automation cohort page %s: mentee not found in DB",
                        page_id,
                    )
                    return

                now = datetime.now(timezone.utc)
                if mentee.telegram_id is None:
                    logger.warning(
                        "Automation cohort page %s: mentee has no telegram_id",
                        page_id,
                    )
                    return
                diffs = await self._sync_cohorts(session, mentee.telegram_id, data, now)
                await session.commit()

                if diffs:
                    from src.services.events.dispatcher import EventDispatcher

                    for diff in diffs:
                        await EventDispatcher.emit(TriggerType.cohort_changed, diff)
        finally:
            await engine.dispose()

    async def backup_pull_cohorts(
        self,
        suppress_emit: bool = False,
        since: datetime | None = None,
    ) -> int:
        if not self.mentee_repo:
            return 0

        if since is not None:
            mentees_data = await self.mentee_repo.get_changed_since(since)
        else:
            mentees_data = await self.mentee_repo.get_all()
        count = 0
        skipped = 0
        all_diffs: list[dict] = []
        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                # Batch prefetch Mentee rows — avoids per-mentee SELECT and lets
                # us echo-filter in memory before doing any write.
                page_ids = [m.page_id for m in mentees_data]
                mentee_by_page: dict = {}
                if page_ids:
                    rows = await session.execute(
                        select(
                            Mentee.notion_page_id,
                            Mentee.telegram_id,
                            Mentee.synced_at,
                        ).where(Mentee.notion_page_id.in_(page_ids))
                    )
                    mentee_by_page = {r.notion_page_id: r for r in rows.all()}

                todo: list[tuple] = []
                for m in mentees_data:
                    row = mentee_by_page.get(m.page_id)
                    if row is None or row.telegram_id is None:
                        skipped += 1
                        continue
                    # Echo guard: skip if our synced_at already covers the
                    # Notion edit (rate-limit partials / clock skew safeguard).
                    if (
                        row.synced_at
                        and m.last_edited_time
                        and row.synced_at >= m.last_edited_time
                    ):
                        skipped += 1
                        continue
                    todo.append((m, row))

                # Batch prefetch current UserCohort snapshot for all todo users
                # in one JOIN — replaces per-user SELECT inside _sync_cohorts.
                old_snapshot: dict[int, dict[tuple[str, str], int]] = defaultdict(dict)
                if todo:
                    user_ids = [row.telegram_id for _, row in todo]
                    snap = await session.execute(
                        select(
                            UserCohort.user_telegram_id,
                            Cohort.id,
                            Cohort.type,
                            Cohort.value,
                        )
                        .join(Cohort, Cohort.id == UserCohort.cohort_id)
                        .where(UserCohort.user_telegram_id.in_(user_ids))
                    )
                    for uid, cid, ctype, cvalue in snap.all():
                        old_snapshot[uid][(ctype, cvalue)] = cid

                now = datetime.now(timezone.utc)
                for m, row in todo:
                    try:
                        async with session.begin_nested():
                            diffs = await self._sync_cohorts(
                                session,
                                row.telegram_id,
                                m,
                                now,
                                old_ids_by_entry=old_snapshot.get(row.telegram_id, {}),
                            )
                            all_diffs.extend(diffs)
                            count += 1
                    except Exception:
                        logger.exception("Error syncing cohort for %s", m.page_id)

                await session.commit()

            if all_diffs and not suppress_emit:
                from src.services.events.dispatcher import EventDispatcher

                for diff in all_diffs:
                    await EventDispatcher.emit(TriggerType.cohort_changed, diff)
        finally:
            await engine.dispose()

        logger.info(
            "Backup pull cohorts: %d synced, %d skipped, %d fetched",
            count,
            skipped,
            len(mentees_data),
        )
        return count

    async def _resolve_mentor_notion_ids(
        self, session: AsyncSession, mentor_telegram_id: int | None
    ) -> list[str] | None:
        if not mentor_telegram_id:
            return None
        client = None
        if self.event_repo:
            client = self.event_repo._client
        elif self.mentee_repo:
            client = self.mentee_repo._client
        elif self.mentor_repo:
            client = self.mentor_repo._client
        if not client:
            return None
        result = await session.execute(
            select(Mentor.email).where(Mentor.telegram_id == mentor_telegram_id)
        )
        email = result.scalar_one_or_none()
        if not email:
            return None
        users = await client.get_users()
        notion_uid = users.get(email.lower())
        if notion_uid:
            return [notion_uid]
        return None

    # ── Push: PostgreSQL → Notion ──────────────────────────────────────

    async def push_mentors(self) -> int:
        if not self.mentor_repo:
            return 0

        engine, factory = _make_session_factory()
        pushed = 0
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Mentor)
                    .options(selectinload(Mentor.user).selectinload(User.role_rel))
                    .where(
                        Mentor.updated_at.isnot(None),
                        Mentor.notion_archived.is_(False),
                        (Mentor.synced_at.is_(None))
                        | (Mentor.updated_at > Mentor.synced_at),
                    )
                )
                mentors = result.scalars().all()

                now = datetime.now(timezone.utc)
                for mentor in mentors:
                    try:
                        if mentor.notion_page_id is None:
                            # Create new Notion page
                            name = (
                                mentor.name
                                or (mentor.user.name if mentor.user else None)
                                or "Unknown"
                            )
                            role_name = (
                                _DB_ROLE_TO_NOTION.get(mentor.user.role_rel.name)
                                if mentor.user and mentor.user.role_rel
                                else "mentor"
                            )
                            page_id = await self.mentor_repo.create_page(
                                name=name,
                                telegram_id=mentor.telegram_id or 0,
                                role=role_name or "mentor",
                            )
                            if page_id:
                                await session.execute(
                                    update(Mentor)
                                    .where(Mentor.id == mentor.id)
                                    .values(notion_page_id=page_id, synced_at=now)
                                )
                                pushed += 1
                        else:
                            props: dict = {}
                            if mentor.user and mentor.user.role_rel:
                                notion_role = _DB_ROLE_TO_NOTION.get(
                                    mentor.user.role_rel.name
                                )
                                if notion_role:
                                    props["Role"] = {"select": {"name": notion_role}}
                            if props:
                                await self.mentor_repo.update_properties(
                                    mentor.notion_page_id, props
                                )

                            await session.execute(
                                update(Mentor)
                                .where(Mentor.id == mentor.id)
                                .values(synced_at=now)
                            )
                            pushed += 1
                    except NotionPageArchivedError:
                        logger.warning(
                            "Mentor %s notion page %s archived; marking notion_archived",
                            mentor.id,
                            mentor.notion_page_id,
                        )
                        await session.execute(
                            update(Mentor)
                            .where(Mentor.id == mentor.id)
                            .values(notion_archived=True, synced_at=now)
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to push mentor %s to Notion: %s",
                            mentor.id,
                            exc,
                        )

                await session.commit()
        finally:
            await engine.dispose()

        if pushed:
            logger.info("Pushed %d mentors to Notion", pushed)
        return pushed

    async def push_mentees(self) -> int:
        if not self.mentee_repo:
            return 0

        engine, factory = _make_session_factory()
        pushed = 0
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Mentee)
                    .options(selectinload(Mentee.mentor))
                    .where(
                        Mentee.updated_at.isnot(None),
                        Mentee.notion_archived.is_(False),
                        (Mentee.synced_at.is_(None))
                        | (Mentee.updated_at > Mentee.synced_at),
                    )
                )
                mentees = result.scalars().all()

                now = datetime.now(timezone.utc)
                for mentee in mentees:
                    try:
                        if mentee.notion_page_id is None:
                            # Create new Notion page
                            username = (
                                mentee.doc_name
                                or (
                                    mentee.user.username
                                    if hasattr(mentee, "user") and mentee.user
                                    else None
                                )
                                or "unknown"
                            )
                            page_id = await self.mentee_repo.create_page(
                                username=username,
                                telegram_id=mentee.telegram_id or 0,
                            )
                            if page_id:
                                await session.execute(
                                    update(Mentee)
                                    .where(Mentee.id == mentee.id)
                                    .values(notion_page_id=page_id, synced_at=now)
                                )
                                pushed += 1
                            continue

                        props: dict = {}
                        if mentee.doc_name:
                            props["Doc name"] = {
                                "title": [{"text": {"content": mentee.doc_name}}]
                            }
                        # Read Status from cohorts
                        status_result = await session.execute(
                            select(Cohort.value)
                            .join(UserCohort, UserCohort.cohort_id == Cohort.id)
                            .where(
                                UserCohort.user_telegram_id == mentee.telegram_id,
                                Cohort.type == "Status",
                            )
                        )
                        notion_status = status_result.scalar_one_or_none()
                        if notion_status:
                            props["Status"] = {"status": {"name": notion_status}}
                        mentor_telegram_id = (
                            mentee.mentor.telegram_id if mentee.mentor else None
                        )
                        mentor_notion_ids = await self._resolve_mentor_notion_ids(
                            session, mentor_telegram_id
                        )
                        if mentor_notion_ids:
                            props["Mentor"] = {
                                "people": [
                                    {"object": "user", "id": uid}
                                    for uid in mentor_notion_ids
                                ]
                            }
                        elif mentee.mentor_id is None:
                            props["Mentor"] = {"people": []}
                        if props:
                            await self.mentee_repo.update_properties(
                                mentee.notion_page_id, props
                            )

                        await session.execute(
                            update(Mentee)
                            .where(Mentee.id == mentee.id)
                            .values(synced_at=now)
                        )
                        pushed += 1
                    except NotionPageArchivedError:
                        logger.warning(
                            "Mentee %s notion page %s archived; marking notion_archived",
                            mentee.id,
                            mentee.notion_page_id,
                        )
                        await session.execute(
                            update(Mentee)
                            .where(Mentee.id == mentee.id)
                            .values(notion_archived=True, synced_at=now)
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to push mentee %s to Notion: %s",
                            mentee.id,
                            exc,
                        )

                await session.commit()
        finally:
            await engine.dispose()

        if pushed:
            logger.info("Pushed %d mentees to Notion", pushed)
        return pushed

    async def push_events(self) -> int:
        if not self.event_repo:
            return 0

        engine, factory = _make_session_factory()
        pushed = 0
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Meeting).where(
                        Meeting.notion_archived.is_(False),
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
                            mentor_notion_ids = await self._resolve_mentor_notion_ids(
                                session, meeting.mentor_telegram_id
                            )
                            page_id = await self.event_repo.create_event(
                                topic=meeting.topic or meeting.description or "Встреча",
                                date=(
                                    meeting.scheduled_at.isoformat()
                                    if meeting.scheduled_at
                                    else None
                                ),
                                event_type=meeting.event_type,
                                status=(
                                    "Отменён"
                                    if meeting.is_cancelled
                                    else "Проведён"
                                    if meeting.completed_at
                                    else "Запланирован"
                                ),
                                mentee_tg_tag=meeting.mentee_telegram_tag,
                                link=meeting.meeting_link,
                                mentor_notion_user_ids=mentor_notion_ids,
                            )
                            if page_id:
                                meeting.notion_page_id = page_id
                                meeting.synced_at = now
                        else:
                            props: dict = {}
                            if meeting.topic:
                                props["Тема"] = {
                                    "title": [{"text": {"content": meeting.topic}}]
                                }
                            if meeting.completed_at:
                                status_name = (
                                    "Отменён" if meeting.is_cancelled else "Проведён"
                                )
                                props["Статус"] = {"status": {"name": status_name}}
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
                            if meeting.event_type:
                                props["Тип"] = {"select": {"name": meeting.event_type}}
                            if meeting.mentee_telegram_tag:
                                props["ТГ тег менти"] = {
                                    "rich_text": [
                                        {
                                            "text": {
                                                "content": meeting.mentee_telegram_tag
                                            }
                                        }
                                    ]
                                }
                            if meeting.meeting_link:
                                props["Ссылка"] = {"url": meeting.meeting_link}
                            if meeting.scheduled_at:
                                props["Дата"] = {
                                    "date": {"start": meeting.scheduled_at.isoformat()}
                                }
                            mentor_notion_ids = await self._resolve_mentor_notion_ids(
                                session, meeting.mentor_telegram_id
                            )
                            if mentor_notion_ids:
                                props["Ментор"] = {
                                    "people": [
                                        {"object": "user", "id": uid}
                                        for uid in mentor_notion_ids
                                    ]
                                }
                            if props:
                                await self.event_repo.update_properties(
                                    meeting.notion_page_id, props
                                )
                            meeting.synced_at = now

                        pushed += 1
                    except NotionPageArchivedError:
                        logger.warning(
                            "Meeting %s notion page %s archived; marking notion_archived",
                            meeting.id,
                            meeting.notion_page_id,
                        )
                        meeting.notion_archived = True
                        meeting.synced_at = now
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

    async def backup_pull_mentors(self) -> int:
        if not self.mentor_repo:
            return 0

        mentors_data = await self.mentor_repo.get_all()
        count = 0
        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                for m in mentors_data:
                    try:
                        async with session.begin_nested():
                            await self._upsert_mentor(session, m, m.page_id)
                            count += 1
                    except Exception:
                        logger.exception("Error syncing mentor %s", m.page_id)

                await session.commit()
        finally:
            await engine.dispose()

        logger.info("Backup pull: %d mentors synced", count)
        return count

    async def backup_pull_mentees(self, suppress_emit: bool = False) -> int:
        if not self.mentee_repo:
            return 0

        mentees_data = await self.mentee_repo.get_all()
        count = 0
        all_events: list[tuple[TriggerType, dict]] = []
        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                for m in mentees_data:
                    try:
                        async with session.begin_nested():
                            events = await self._upsert_mentee(session, m, m.page_id)
                            all_events.extend(events)
                            count += 1
                    except Exception:
                        logger.exception("Error syncing mentee %s", m.page_id)

                await session.commit()

            if all_events and not suppress_emit:
                from src.services.events.dispatcher import EventDispatcher

                for trigger_type, ctx in all_events:
                    await EventDispatcher.emit(trigger_type, ctx)
        finally:
            await engine.dispose()

        logger.info("Backup pull: %d mentees synced", count)
        return count

    async def backup_pull_events(self) -> int:
        if not self.event_repo:
            return 0

        events = await self.event_repo.get_all()
        count = 0
        reschedule_targets: list[tuple[int, datetime]] = []
        engine, factory = _make_session_factory()
        try:
            async with factory() as session:
                for ev in events:
                    try:
                        async with session.begin_nested():
                            result = await session.execute(
                                select(Meeting).where(
                                    Meeting.notion_page_id == ev.page_id
                                )
                            )
                            meeting = result.scalar_one_or_none()

                            now = datetime.now(timezone.utc)
                            mentor_tid = await _resolve_mentor_telegram_id(
                                session, ev.mentor_name
                            )
                            mentee_tids = await _resolve_mentee_ids(
                                session, ev.mentee_tg_tag
                            )
                            all_user_ids = (
                                [mentor_tid] if mentor_tid else []
                            ) + mentee_tids

                            if meeting:
                                if (
                                    meeting.synced_at
                                    and ev.last_edited_time
                                    and meeting.synced_at >= ev.last_edited_time
                                ):
                                    await _ensure_meeting_users(
                                        session, meeting.id, user_ids=all_user_ids
                                    )
                                    continue
                                meeting.notion_archived = False
                                meeting.topic = ev.topic
                                meeting.event_type = ev.event_type
                                meeting.mentee_telegram_tag = ev.mentee_tg_tag
                                meeting.recording_link = ev.recording
                                meeting.summary = ev.summary
                                meeting.action_items = ev.action_items
                                meeting.project = ev.project
                                if mentor_tid:
                                    meeting.mentor_telegram_id = mentor_tid
                                new_scheduled_at = _parse_iso_date(ev.date)
                                if (
                                    new_scheduled_at is not None
                                    and not meeting.is_cancelled
                                    and not _same_moment(
                                        meeting.scheduled_at, new_scheduled_at
                                    )
                                ):
                                    reschedule_targets.append(
                                        (meeting.id, new_scheduled_at)
                                    )
                                if ev.link:
                                    meeting.meeting_link = ev.link
                                if (
                                    ev.status in ("Проведён", "Отменён")
                                    and not meeting.completed_at
                                ):
                                    meeting.completed_at = now
                                if ev.status == "Отменён":
                                    meeting.is_cancelled = True
                                elif ev.status == "Проведён":
                                    meeting.is_cancelled = False
                                meeting.synced_at = now
                                await _ensure_meeting_users(
                                    session, meeting.id, user_ids=all_user_ids
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
                                    mentor_telegram_id=mentor_tid,
                                )
                                if ev.status in ("Проведён", "Отменён"):
                                    new_meeting.completed_at = now
                                if ev.status == "Отменён":
                                    new_meeting.is_cancelled = True
                                session.add(new_meeting)
                                await session.flush()
                                await _ensure_meeting_users(
                                    session, new_meeting.id, user_ids=all_user_ids
                                )

                            count += 1
                    except Exception:
                        logger.exception("Error syncing event %s", ev.page_id)

                await session.commit()
        finally:
            await engine.dispose()

        for meeting_id, new_dt in reschedule_targets:
            try:
                await self._apply_notion_reschedule(meeting_id, new_dt)
            except Exception:
                logger.exception(
                    "Error applying notion reschedule for meeting %s", meeting_id
                )

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


_worker_sync_service: NotionSyncServiceV2 | None = None


@asynccontextmanager
async def sync_service_scope() -> AsyncIterator[NotionSyncServiceV2 | None]:
    """Yield a shared NotionSyncServiceV2 bound to the Celery worker's loop.

    With the persistent worker event loop (src/tasks/_db.py), httpx clients
    are safe to keep alive for the worker's lifetime. Repos are built lazily
    on first use and closed once at worker shutdown via close_notion_clients().
    """
    global _worker_sync_service
    if _worker_sync_service is None:
        mentor_repo, mentee_repo, event_repo = _build_repos()
        if not any((mentor_repo, mentee_repo, event_repo)):
            yield None
            return
        _worker_sync_service = NotionSyncServiceV2(mentor_repo, mentee_repo, event_repo)
    yield _worker_sync_service


async def close_notion_clients() -> None:
    """Close cached Notion HTTP clients. Called from worker shutdown cleanup."""
    global _worker_sync_service
    service = _worker_sync_service
    if service is None:
        return
    for repo in (service.mentor_repo, service.mentee_repo, service.event_repo):
        if repo is None:
            continue
        try:
            await repo._client.close()
        except Exception:
            logger.warning("Failed to close cached Notion client", exc_info=True)
    _worker_sync_service = None
