from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from src.core.database import async_session_maker
from src.models.survey_session import SessionStatus, SurveyAnswer, SurveySession


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

            await session.refresh(survey_session)
            return survey_session, False

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
            existing = await session.execute(
                select(SurveyAnswer).where(
                    SurveyAnswer.session_id == session_id,
                    SurveyAnswer.question_id == question_id,
                )
            )
            answer = existing.scalar_one_or_none()

            if answer:
                answer.value_text = value_text
                answer.value_int = value_int
                answer.value_choice = value_choice
            else:
                answer = SurveyAnswer(
                    session_id=session_id,
                    question_id=question_id,
                    value_text=value_text,
                    value_int=value_int,
                    value_choice=value_choice,
                )
                session.add(answer)

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
