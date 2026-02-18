import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import get_survey_service
from src.api.schemas.survey import (
    SurveyAnswer,
    SurveyStateResponse,
    SurveySubmitRequest,
    SurveySubmitResponse,
)
from src.services.survey import (
    CallNotFoundError,
    SurveyNotAvailableError,
    SurveyService,
    SurveyStudentNotFoundError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calls", tags=["survey"])


@router.get("/{call_id}/survey", response_model=SurveyStateResponse)
async def get_call_survey(
    call_id: int,
    service: SurveyService = Depends(get_survey_service),
) -> SurveyStateResponse:
    try:
        state, response = await service.get_survey_state(call_id)
    except CallNotFoundError as exc:
        logger.info("Survey call not found: call_id=%s", call_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Созвон не найден") from exc

    return SurveyStateResponse(
        call_id=call_id,
        status=state,
        questions=service.build_questions(),
        response=SurveyAnswer.model_validate(response) if response else None,
    )


@router.post("/{call_id}/survey", response_model=SurveySubmitResponse)
async def submit_call_survey(
    call_id: int,
    payload: SurveySubmitRequest,
    service: SurveyService = Depends(get_survey_service),
) -> SurveySubmitResponse:
    try:
        response, already_submitted = await service.submit_survey(call_id=call_id, payload=payload)
    except CallNotFoundError as exc:
        logger.info("Survey submit call not found: call_id=%s", call_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Созвон не найден") from exc
    except SurveyNotAvailableError as exc:
        logger.info("Survey not available for call: call_id=%s", call_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Опрос доступен только после завершения созвона",
        ) from exc
    except SurveyStudentNotFoundError as exc:
        logger.warning("Survey submit failed, no student in call: call_id=%s", call_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Не удалось определить ученика для созвона",
        ) from exc

    return SurveySubmitResponse(
        call_id=call_id,
        already_submitted=already_submitted,
        response=SurveyAnswer.model_validate(response),
    )
