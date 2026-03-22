from fastapi import APIRouter, HTTPException, status

from src.dao.survey_template import SurveyTemplateDAO
from src.services.survey_session import (
    SessionNotFoundError,
    SurveySessionService,
)

router = APIRouter(prefix="/survey", tags=["survey"])


@router.get("/templates")
async def list_templates():
    templates = await SurveyTemplateDAO.get_all_active()
    return [
        {
            "id": t.id,
            "title": t.title,
            "slug": t.slug,
            "description": t.description,
            "questions_count": len(t.questions) if t.questions else 0,
        }
        for t in templates
    ]


@router.get("/templates/{slug}")
async def get_template(slug: str):
    template = await SurveyTemplateDAO.get_by_slug(slug)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return {
        "id": template.id,
        "title": template.title,
        "slug": template.slug,
        "description": template.description,
        "questions": [
            {
                "id": q.id,
                "sort_order": q.sort_order,
                "title": q.title,
                "question_type": q.question_type.value,
                "is_required": q.is_required,
                "config": q.config,
                "options": [
                    {"value": o.value, "label": o.label} for o in q.options
                ],
            }
            for q in template.questions
        ],
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: int):
    service = SurveySessionService()
    try:
        session = await service.get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from exc

    return {
        "id": session.id,
        "template_id": session.template_id,
        "respondent_id": session.respondent_id,
        "context_type": session.context_type,
        "context_id": session.context_id,
        "status": session.status.value,
        "answers": [
            {
                "question_id": a.question_id,
                "value_text": a.value_text,
                "value_int": a.value_int,
                "value_choice": a.value_choice,
            }
            for a in session.answers
        ],
    }
