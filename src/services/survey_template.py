from typing import Optional

from src.dao.survey_template import SurveyTemplateDAO
from src.models.survey_template import SurveyTemplate


class TemplateNotFoundError(Exception):
    pass


class SlugAlreadyExistsError(Exception):
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
        description: str | None = None,
        target_role_id: int | None = None,
        created_by: int | None = None,
        questions: list[dict] | None = None,
    ) -> SurveyTemplate:
        existing = await SurveyTemplateDAO.get_by_slug(slug)
        if existing:
            raise SlugAlreadyExistsError

        template = await SurveyTemplateDAO.create(
            title=title,
            slug=slug,
            description=description,
            target_role_id=target_role_id,
            created_by=created_by,
        )

        if questions:
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
