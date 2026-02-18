from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from src.core.database import async_session_maker
from src.models.meeting import Meeting
from src.models.survey import SurveyResponse


class SurveyDAO:
    @classmethod
    async def get_call_with_participants(cls, call_id: int) -> Optional[Meeting]:
        async with async_session_maker() as session:
            query = (
                select(Meeting)
                .where(Meeting.id == call_id)
                .options(
                    joinedload(Meeting.participants),
                    joinedload(Meeting.survey_response),
                )
            )
            result = await session.execute(query)
            result = result.unique()
            return result.scalar_one_or_none()

    @classmethod
    async def get_response(cls, call_id: int) -> Optional[SurveyResponse]:
        async with async_session_maker() as session:
            query = select(SurveyResponse).where(SurveyResponse.call_id == call_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def submit_response(
        cls,
        *,
        call_id: int,
        student_id: int,
        duration_option: str,
        mentor_style: int,
        knowledge_depth: int,
        understanding: int,
        comment: str | None,
    ) -> tuple[SurveyResponse, bool]:
        async with async_session_maker() as session:
            try:
                async with session.begin():
                    existing = await session.execute(
                        select(SurveyResponse).where(SurveyResponse.call_id == call_id)
                    )
                    existing_response = existing.scalar_one_or_none()
                    if existing_response:
                        return existing_response, True

                    response = SurveyResponse(
                        call_id=call_id,
                        student_id=student_id,
                        duration_option=duration_option,
                        mentor_style=mentor_style,
                        knowledge_depth=knowledge_depth,
                        understanding=understanding,
                        comment=comment,
                    )

                    session.add(response)
            except IntegrityError:
                await session.rollback()
                existing = await session.execute(
                    select(SurveyResponse).where(SurveyResponse.call_id == call_id)
                )
                existing_response = existing.scalar_one_or_none()
                if existing_response:
                    return existing_response, True
                raise

            await session.refresh(response)
            return response, False
