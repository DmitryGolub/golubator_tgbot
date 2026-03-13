from fastapi import APIRouter, HTTPException, status

from src.api.schemas.survey import SurveyStateResponse, SurveySubmitResponse
from src.services.survey import (
    CallNotFoundError,
    SurveyNotAvailableError,
    SurveyService,
)
from src.survey.schemas import (
    SurveyAnswer,
    SurveyQuestion,
    SurveyStatus,
    SurveySubmitRequest,
)

router = APIRouter(prefix="/survey", tags=["survey"])


@router.get("/questions", response_model=list[SurveyQuestion])
async def get_survey_questions() -> list[SurveyQuestion]:
    service = SurveyService()
    return service.build_questions()


@router.get("/{call_id}", response_model=SurveyStateResponse)
async def get_survey_state(call_id: int) -> SurveyStateResponse:
    service = SurveyService()
    try:
        survey_status, response = await service.get_survey_state(call_id)
    except CallNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Созвон не найден",
        ) from exc

    answer = SurveyAnswer.model_validate(response) if response else None
    questions = service.build_questions() if survey_status == SurveyStatus.available else None
    return SurveyStateResponse(
        status=survey_status,
        response=answer,
        questions=questions,
    )


@router.post("/{call_id}", response_model=SurveySubmitResponse)
async def submit_survey(
    call_id: int,
    payload: SurveySubmitRequest,
) -> SurveySubmitResponse:
    service = SurveyService()
    try:
        response, already_submitted = await service.submit_survey(
            call_id=call_id,
            payload=payload,
        )
    except CallNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Созвон не найден",
        ) from exc
    except SurveyNotAvailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Опрос пока недоступен",
        ) from exc

    return SurveySubmitResponse(
        already_submitted=already_submitted,
        response=SurveyAnswer.model_validate(response),
    )
