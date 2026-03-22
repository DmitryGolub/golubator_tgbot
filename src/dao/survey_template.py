from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.database import async_session_maker
from src.models.survey_template import (
    SurveyQuestion,
    SurveyQuestionOption,
    SurveyTemplate,
)


class SurveyTemplateDAO:
    @classmethod
    async def get_all_active(cls) -> list[SurveyTemplate]:
        async with async_session_maker() as session:
            query = (
                select(SurveyTemplate)
                .where(SurveyTemplate.is_active.is_(True))
                .order_by(SurveyTemplate.id)
            )
            result = await session.execute(query)
            return list(result.unique().scalars().all())

    @classmethod
    async def get_by_id(cls, template_id: int) -> Optional[SurveyTemplate]:
        async with async_session_maker() as session:
            query = (
                select(SurveyTemplate)
                .where(SurveyTemplate.id == template_id)
                .options(
                    joinedload(SurveyTemplate.questions).joinedload(
                        SurveyQuestion.options
                    ),
                )
            )
            result = await session.execute(query)
            return result.unique().scalar_one_or_none()

    @classmethod
    async def get_by_slug(cls, slug: str) -> Optional[SurveyTemplate]:
        async with async_session_maker() as session:
            query = (
                select(SurveyTemplate)
                .where(SurveyTemplate.slug == slug)
                .options(
                    joinedload(SurveyTemplate.questions).joinedload(
                        SurveyQuestion.options
                    ),
                )
            )
            result = await session.execute(query)
            return result.unique().scalar_one_or_none()

    @classmethod
    async def create(
        cls,
        *,
        title: str,
        slug: str,
        description: str | None = None,
        target_role_id: int | None = None,
        created_by: int | None = None,
    ) -> SurveyTemplate:
        async with async_session_maker() as session:
            template = SurveyTemplate(
                title=title,
                slug=slug,
                description=description,
                target_role_id=target_role_id,
                created_by=created_by,
            )
            session.add(template)
            await session.commit()
            await session.refresh(template)
            return template

    @classmethod
    async def add_question(
        cls,
        *,
        template_id: int,
        sort_order: int,
        title: str,
        question_type: str,
        is_required: bool = True,
        config: dict | None = None,
        options: list[dict] | None = None,
    ) -> SurveyQuestion:
        async with async_session_maker() as session:
            question = SurveyQuestion(
                template_id=template_id,
                sort_order=sort_order,
                title=title,
                question_type=question_type,
                is_required=is_required,
                config=config,
            )
            session.add(question)
            await session.flush()

            if options:
                for i, opt in enumerate(options):
                    option = SurveyQuestionOption(
                        question_id=question.id,
                        sort_order=i + 1,
                        value=opt["value"],
                        label=opt["label"],
                    )
                    session.add(option)

            await session.commit()
            await session.refresh(question)
            return question

    @classmethod
    async def get_question_by_id(cls, question_id: int) -> Optional[SurveyQuestion]:
        async with async_session_maker() as session:
            return await session.get(SurveyQuestion, question_id)

    @classmethod
    async def delete(cls, template_id: int) -> bool:
        async with async_session_maker() as session:
            template = await session.get(SurveyTemplate, template_id)
            if not template:
                return False
            await session.delete(template)
            await session.commit()
            return True

    @classmethod
    async def set_active(
        cls, template_id: int, is_active: bool
    ) -> Optional[SurveyTemplate]:
        async with async_session_maker() as session:
            template = await session.get(SurveyTemplate, template_id)
            if not template:
                return None
            template.is_active = is_active
            await session.commit()
            await session.refresh(template)
            return template
