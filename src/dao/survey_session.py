from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from src.core.database import async_session_maker
from src.models.survey_session import SessionStatus, SurveyAnswer, SurveySession


_ALLOWED_ESCALATION_FIELDS = frozenset(
    {
        "reminder_sent_at",
        "mentor_notified_at",
        "escalated_at",
        "is_escalatable",
    }
)


class SurveySessionDAO:
    @classmethod
    async def create(
        cls,
        *,
        template_id: int,
        respondent_id: int,
        context_type: str | None = None,
        context_id: str | None = None,
    ) -> tuple[SurveySession, bool]:
        """Create a session. Returns (session, already_existed)."""
        async with async_session_maker() as session:
            try:
                async with session.begin():
                    existing = await session.execute(
                        select(SurveySession).where(
                            SurveySession.template_id == template_id,
                            SurveySession.respondent_id == respondent_id,
                            SurveySession.context_type == context_type,
                            SurveySession.context_id == context_id,
                        )
                    )
                    existing_session = existing.scalar_one_or_none()
                    if existing_session:
                        return existing_session, True

                    survey_session = SurveySession(
                        template_id=template_id,
                        respondent_id=respondent_id,
                        context_type=context_type,
                        context_id=context_id,
                        status=SessionStatus.pending,
                    )
                    session.add(survey_session)
                await session.refresh(survey_session)
            except IntegrityError:
                await session.rollback()
                existing = await session.execute(
                    select(SurveySession).where(
                        SurveySession.template_id == template_id,
                        SurveySession.respondent_id == respondent_id,
                        SurveySession.context_type == context_type,
                        SurveySession.context_id == context_id,
                    )
                )
                existing_session = existing.scalar_one_or_none()
                if existing_session:
                    return existing_session, True
                raise

            return survey_session, False

    @classmethod
    async def get_pending_for_respondent(
        cls, respondent_id: int
    ) -> list[SurveySession]:
        async with async_session_maker() as session:
            query = (
                select(SurveySession)
                .where(
                    SurveySession.respondent_id == respondent_id,
                    SurveySession.status.in_(
                        [SessionStatus.pending, SessionStatus.in_progress]
                    ),
                )
                .order_by(SurveySession.created_at.desc())
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    @classmethod
    async def get_by_id(cls, session_id: int) -> Optional[SurveySession]:
        async with async_session_maker() as session:
            query = (
                select(SurveySession)
                .where(SurveySession.id == session_id)
                .options(
                    joinedload(SurveySession.template),
                    joinedload(SurveySession.answers).joinedload(SurveyAnswer.question),
                )
            )
            result = await session.execute(query)
            return result.unique().scalar_one_or_none()

    @classmethod
    async def get_completed_by_template(cls, template_id: int) -> list[SurveySession]:
        async with async_session_maker() as session:
            query = (
                select(SurveySession)
                .where(
                    SurveySession.template_id == template_id,
                    SurveySession.status == SessionStatus.completed,
                )
                .options(
                    joinedload(SurveySession.answers).joinedload(SurveyAnswer.question),
                )
                .order_by(SurveySession.completed_at.desc())
            )
            result = await session.execute(query)
            return list(result.unique().scalars().all())

    @classmethod
    async def find_for_respondent(
        cls,
        *,
        template_id: int,
        respondent_id: int,
        context_type: str | None = None,
        context_id: str | None = None,
    ) -> Optional[SurveySession]:
        async with async_session_maker() as session:
            query = select(SurveySession).where(
                SurveySession.template_id == template_id,
                SurveySession.respondent_id == respondent_id,
                SurveySession.context_type == context_type,
                SurveySession.context_id == context_id,
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def start(cls, session_id: int) -> Optional[SurveySession]:
        async with async_session_maker() as session:
            survey_session = await session.get(SurveySession, session_id)
            if not survey_session:
                return None
            survey_session.status = SessionStatus.in_progress
            survey_session.started_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(survey_session)
            return survey_session

    @classmethod
    async def save_answer(
        cls,
        *,
        session_id: int,
        question_id: int,
        value_text: str | None = None,
        value_int: int | None = None,
        value_choice: list | None = None,
    ) -> SurveyAnswer:
        async with async_session_maker() as session:
            stmt = (
                pg_insert(SurveyAnswer)
                .values(
                    session_id=session_id,
                    question_id=question_id,
                    value_text=value_text,
                    value_int=value_int,
                    value_choice=value_choice,
                )
                .on_conflict_do_update(
                    constraint="uq_survey_answer_unique",
                    set_=dict(
                        value_text=value_text,
                        value_int=value_int,
                        value_choice=value_choice,
                    ),
                )
                .returning(SurveyAnswer)
            )
            result = await session.execute(stmt)
            answer = result.scalar_one()
            await session.commit()
            await session.refresh(answer)
            return answer

    @classmethod
    async def complete(cls, session_id: int) -> Optional[SurveySession]:
        async with async_session_maker() as session:
            survey_session = await session.get(SurveySession, session_id)
            if not survey_session:
                return None
            survey_session.status = SessionStatus.completed
            survey_session.completed_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(survey_session)
            return survey_session

    @classmethod
    async def get_overdue_sessions(cls, min_age_hours: int = 24) -> list[SurveySession]:
        """Get sessions due for reminder/escalation handling."""
        from src.models.survey_template import SurveyTemplate, TemplateKind

        cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
        async with async_session_maker() as session:
            query = (
                select(SurveySession)
                .join(SurveyTemplate, SurveySession.template_id == SurveyTemplate.id)
                .where(
                    SurveySession.status.in_(
                        [SessionStatus.pending, SessionStatus.in_progress]
                    ),
                    SurveyTemplate.kind != TemplateKind.broadcast,
                    or_(
                        SurveyTemplate.reminder_interval_minutes.isnot(None),
                        SurveySession.is_escalatable.is_(True),
                    ),
                    or_(
                        SurveyTemplate.reminder_interval_minutes.isnot(None),
                        SurveySession.created_at < cutoff,
                    ),
                )
                .options(joinedload(SurveySession.template))
                .order_by(SurveySession.created_at)
            )
            result = await session.execute(query)
            return list(result.unique().scalars().all())

    @classmethod
    async def update_escalation_field(cls, session_id: int, field: str, value) -> None:
        if field not in _ALLOWED_ESCALATION_FIELDS:
            raise ValueError(f"Invalid escalation field: {field!r}")
        async with async_session_maker() as db:
            await db.execute(
                update(SurveySession)
                .where(SurveySession.id == session_id)
                .values(**{field: value})
            )
            await db.commit()

    @classmethod
    async def get_recent_completed(
        cls, *, template_id: int, respondent_id: int, limit: int
    ) -> list[SurveySession]:
        """Return last N completed sessions for the given respondent + template."""
        async with async_session_maker() as db:
            query = (
                select(SurveySession)
                .where(
                    SurveySession.template_id == template_id,
                    SurveySession.respondent_id == respondent_id,
                    SurveySession.status == SessionStatus.completed,
                )
                .options(
                    joinedload(SurveySession.answers).joinedload(SurveyAnswer.question)
                )
                .order_by(SurveySession.completed_at.desc())
                .limit(limit)
            )
            result = await db.execute(query)
            return list(result.unique().scalars().all())

    @classmethod
    async def find_paired(
        cls, *, paired_slug: str, context_id: str
    ) -> SurveySession | None:
        """Find a completed session by the slug of a paired template and context_id."""
        async with async_session_maker() as db:
            from src.models.survey_template import SurveyTemplate

            query = (
                select(SurveySession)
                .join(SurveyTemplate, SurveySession.template_id == SurveyTemplate.id)
                .where(
                    SurveyTemplate.slug == paired_slug,
                    SurveySession.context_id == context_id,
                    SurveySession.status == SessionStatus.completed,
                )
                .options(
                    joinedload(SurveySession.answers).joinedload(SurveyAnswer.question)
                )
                .limit(1)
            )
            result = await db.execute(query)
            return result.unique().scalar_one_or_none()
