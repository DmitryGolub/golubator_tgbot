from typing import Optional

from src.dao.survey_template import SurveyTemplateDAO
from src.models.survey_template import (
    SurveyQuestion,
    SurveyQuestionOption,
    SurveyTemplate,
    TemplateKind,
)


class TemplateNotFoundError(Exception):
    pass


class SlugAlreadyExistsError(Exception):
    pass


class QuestionNotFoundError(Exception):
    pass


class OptionNotFoundError(Exception):
    pass


class SurveyTemplateService:
    async def list_active(self) -> list[SurveyTemplate]:
        return await SurveyTemplateDAO.get_all_active()

    async def get(self, template_id: int) -> SurveyTemplate:
        template = await SurveyTemplateDAO.get_by_id(template_id)
        if not template:
            raise TemplateNotFoundError
        return template

    async def get_by_slug(self, slug: str) -> Optional[SurveyTemplate]:
        return await SurveyTemplateDAO.get_by_slug(slug)

    async def create(
        self,
        *,
        title: str,
        slug: str,
        kind: TemplateKind = TemplateKind.survey,
        description: str | None = None,
        body: str | None = None,
        target_role_id: int | None = None,
        created_by: int | None = None,
        questions: list[dict] | None = None,
    ) -> SurveyTemplate:
        if kind == TemplateKind.broadcast and not (body or "").strip():
            raise ValueError("Broadcast template requires non-empty body")

        existing = await SurveyTemplateDAO.get_by_slug(slug)
        if existing:
            raise SlugAlreadyExistsError

        template = await SurveyTemplateDAO.create(
            title=title,
            slug=slug,
            kind=kind,
            description=description,
            body=body,
            target_role_id=target_role_id,
            created_by=created_by,
        )

        if questions and kind == TemplateKind.survey:
            await SurveyTemplateDAO.add_questions_batch(
                template_id=template.id,
                questions=questions,
            )

        return await SurveyTemplateDAO.get_by_id(template.id)

    async def add_question(
        self,
        *,
        template_id: int,
        sort_order: int,
        title: str,
        question_type: str,
        is_required: bool = True,
        config: dict | None = None,
        options: list[dict] | None = None,
    ):
        template = await SurveyTemplateDAO.get_by_id(template_id)
        if not template:
            raise TemplateNotFoundError

        return await SurveyTemplateDAO.add_question(
            template_id=template_id,
            sort_order=sort_order,
            title=title,
            question_type=question_type,
            is_required=is_required,
            config=config,
            options=options,
        )

    async def delete(self, template_id: int) -> None:
        deleted = await SurveyTemplateDAO.delete(template_id)
        if not deleted:
            raise TemplateNotFoundError

    async def toggle_active(self, template_id: int, is_active: bool) -> SurveyTemplate:
        template = await SurveyTemplateDAO.set_active(template_id, is_active)
        if not template:
            raise TemplateNotFoundError
        return template

    # --- Edit operations ---

    async def update_template(self, template_id: int, **kwargs) -> SurveyTemplate:
        if "slug" in kwargs:
            existing = await SurveyTemplateDAO.get_by_slug(kwargs["slug"])
            if existing and existing.id != template_id:
                raise SlugAlreadyExistsError
        template = await SurveyTemplateDAO.update_template(template_id, **kwargs)
        if not template:
            raise TemplateNotFoundError
        # Re-fetch with relationships loaded
        return await self.get(template_id)

    async def get_question(self, question_id: int) -> SurveyQuestion:
        question = await SurveyTemplateDAO.get_question_with_options(question_id)
        if not question:
            raise QuestionNotFoundError
        return question

    async def update_question(self, question_id: int, **kwargs) -> SurveyQuestion:
        question = await SurveyTemplateDAO.update_question(question_id, **kwargs)
        if not question:
            raise QuestionNotFoundError
        return await self.get_question(question_id)

    async def delete_question(self, question_id: int) -> None:
        deleted = await SurveyTemplateDAO.delete_question(question_id)
        if not deleted:
            raise QuestionNotFoundError

    async def swap_question_order(
        self, question_id: int, direction: str
    ) -> Optional[SurveyQuestion]:
        return await SurveyTemplateDAO.swap_question_order(question_id, direction)

    async def add_option(
        self, *, question_id: int, value: str, label: str
    ) -> SurveyQuestionOption:
        return await SurveyTemplateDAO.add_option(
            question_id=question_id, value=value, label=label
        )

    async def delete_option(self, option_id: int) -> None:
        deleted = await SurveyTemplateDAO.delete_option(option_id)
        if not deleted:
            raise OptionNotFoundError

    async def update_option(self, option_id: int, **kwargs) -> SurveyQuestionOption:
        option = await SurveyTemplateDAO.update_option(option_id, **kwargs)
        if not option:
            raise OptionNotFoundError
        return option

    async def replace_question_options(
        self, question_id: int, options: list[dict]
    ) -> None:
        await SurveyTemplateDAO.replace_question_options(question_id, options)
