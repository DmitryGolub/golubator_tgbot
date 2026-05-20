from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import joinedload

from src.core.database import async_session_maker
from src.models.survey_template import (
    SurveyQuestion,
    SurveyQuestionOption,
    SurveyTemplate,
    TemplateKind,
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
        kind: TemplateKind = TemplateKind.survey,
        description: str | None = None,
        body: str | None = None,
        target_role_id: int | None = None,
        created_by: int | None = None,
    ) -> SurveyTemplate:
        async with async_session_maker() as session:
            template = SurveyTemplate(
                title=title,
                slug=slug,
                kind=kind,
                description=description,
                body=body,
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
    async def add_questions_batch(
        cls,
        *,
        template_id: int,
        questions: list[dict],
    ) -> None:
        async with async_session_maker() as session:
            for i, q in enumerate(questions):
                question = SurveyQuestion(
                    template_id=template_id,
                    sort_order=i + 1,
                    title=q["title"],
                    question_type=q["question_type"],
                    is_required=q.get("is_required", True),
                    config=q.get("config"),
                )
                session.add(question)
                if q.get("options"):
                    await session.flush()
                    for j, opt in enumerate(q["options"]):
                        session.add(
                            SurveyQuestionOption(
                                question_id=question.id,
                                sort_order=j + 1,
                                value=opt["value"],
                                label=opt["label"],
                            )
                        )
            await session.commit()

    @classmethod
    async def get_question_by_id(cls, question_id: int) -> Optional[SurveyQuestion]:
        async with async_session_maker() as session:
            return await session.get(SurveyQuestion, question_id)

    @classmethod
    async def get_question_with_options(
        cls, question_id: int
    ) -> Optional[SurveyQuestion]:
        async with async_session_maker() as session:
            query = (
                select(SurveyQuestion)
                .where(SurveyQuestion.id == question_id)
                .options(joinedload(SurveyQuestion.options))
            )
            result = await session.execute(query)
            return result.unique().scalar_one_or_none()

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

    # --- Edit operations ---

    @classmethod
    async def update_template(
        cls, template_id: int, **kwargs
    ) -> Optional[SurveyTemplate]:
        async with async_session_maker() as session:
            template = await session.get(SurveyTemplate, template_id)
            if not template:
                return None
            for key, value in kwargs.items():
                setattr(template, key, value)
            await session.commit()
            await session.refresh(template)
            return template

    @classmethod
    async def update_question(
        cls, question_id: int, **kwargs
    ) -> Optional[SurveyQuestion]:
        async with async_session_maker() as session:
            question = await session.get(SurveyQuestion, question_id)
            if not question:
                return None
            for key, value in kwargs.items():
                setattr(question, key, value)
            await session.commit()
            await session.refresh(question)
            return question

    @classmethod
    async def delete_question(cls, question_id: int) -> bool:
        async with async_session_maker() as session:
            question = await session.get(SurveyQuestion, question_id)
            if not question:
                return False
            template_id = question.template_id
            deleted_order = question.sort_order
            await session.delete(question)
            await session.flush()
            # Shift subsequent questions down (single UPDATE is valid under
            # Postgres unique constraint checks at statement end).
            await session.execute(
                update(SurveyQuestion)
                .where(
                    SurveyQuestion.template_id == template_id,
                    SurveyQuestion.sort_order > deleted_order,
                )
                .values(sort_order=SurveyQuestion.sort_order - 1)
            )
            await session.commit()
            return True

    @classmethod
    async def swap_question_order(
        cls, question_id: int, direction: str
    ) -> Optional[SurveyQuestion]:
        async with async_session_maker() as session:
            question = await session.get(SurveyQuestion, question_id)
            if not question:
                return None

            if direction == "up":
                neighbor_order = question.sort_order - 1
            elif direction == "down":
                neighbor_order = question.sort_order + 1
            else:
                return None

            neighbor_query = select(SurveyQuestion).where(
                SurveyQuestion.template_id == question.template_id,
                SurveyQuestion.sort_order == neighbor_order,
            )
            neighbor = (await session.execute(neighbor_query)).scalar_one_or_none()
            if not neighbor:
                return None

            original_a = question.sort_order
            original_b = neighbor.sort_order

            # Use temp=-1 to bypass unique constraint
            question.sort_order = -1
            await session.flush()
            neighbor.sort_order = original_a
            await session.flush()
            question.sort_order = original_b
            await session.commit()
            await session.refresh(question)
            return question

    @classmethod
    async def update_option(
        cls, option_id: int, **kwargs
    ) -> Optional[SurveyQuestionOption]:
        async with async_session_maker() as session:
            option = await session.get(SurveyQuestionOption, option_id)
            if not option:
                return None
            for key, value in kwargs.items():
                setattr(option, key, value)
            await session.commit()
            await session.refresh(option)
            return option

    @classmethod
    async def delete_option(cls, option_id: int) -> bool:
        async with async_session_maker() as session:
            option = await session.get(SurveyQuestionOption, option_id)
            if not option:
                return False
            question_id = option.question_id
            deleted_order = option.sort_order
            await session.delete(option)
            await session.flush()
            await session.execute(
                update(SurveyQuestionOption)
                .where(
                    SurveyQuestionOption.question_id == question_id,
                    SurveyQuestionOption.sort_order > deleted_order,
                )
                .values(sort_order=SurveyQuestionOption.sort_order - 1)
            )
            await session.commit()
            return True

    @classmethod
    async def add_option(
        cls, *, question_id: int, value: str, label: str
    ) -> SurveyQuestionOption:
        async with async_session_maker() as session:
            max_order_query = select(SurveyQuestionOption.sort_order).where(
                SurveyQuestionOption.question_id == question_id
            )
            result = await session.execute(max_order_query)
            orders = [row for row in result.scalars().all()]
            next_order = (max(orders) + 1) if orders else 1

            option = SurveyQuestionOption(
                question_id=question_id,
                sort_order=next_order,
                value=value,
                label=label,
            )
            session.add(option)
            await session.commit()
            await session.refresh(option)
            return option

    @classmethod
    async def replace_question_options(
        cls, question_id: int, options: list[dict]
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(SurveyQuestionOption).where(
                    SurveyQuestionOption.question_id == question_id
                )
            )
            await session.flush()
            for i, opt in enumerate(options):
                session.add(
                    SurveyQuestionOption(
                        question_id=question_id,
                        sort_order=i + 1,
                        value=opt["value"],
                        label=opt["label"],
                    )
                )
            await session.commit()
