import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import DataError, OperationalError, ProgrammingError, SQLAlchemyError

from src.api.dependencies import get_mentor_feedback_service
from src.api.schemas.mentor_feedback import (
    MentorFeedbackCreateRequest,
    MentorFeedbackResponse,
)
from src.services.mentor_feedback import (
    CallNotFoundError,
    MentorFeedbackAlreadyExistsError,
    MentorFeedbackService,
    MentorNotInCallError,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calls", tags=["mentor-feedback"])
CallIdPath = Annotated[int, Path(ge=1, le=2147483647)]
DB_ERRORS = (OperationalError, ProgrammingError, SQLAlchemyError)

try:
    import asyncpg

    DB_ERRORS = DB_ERRORS + (asyncpg.PostgresError,)
except ImportError:
    asyncpg = None


@router.post(
    "/{call_id}/mentor-feedback",
    response_model=MentorFeedbackResponse,
)
async def create_mentor_feedback(
    call_id: CallIdPath,
    payload: MentorFeedbackCreateRequest,
    service: MentorFeedbackService = Depends(get_mentor_feedback_service),
) -> MentorFeedbackResponse:
    try:
        feedback = await service.create_feedback(
            call_id=call_id,
            mentor_id=payload.mentor_id,
            payload=payload,
        )
        return MentorFeedbackResponse.model_validate(feedback)
    except CallNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Созвон не найден",
        ) from exc
    except MentorFeedbackAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Фидбек для этого созвона уже отправлен",
        ) from exc
    except MentorNotInCallError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ментор не привязан к этому созвону",
        ) from exc
    except DataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректный call_id",
        ) from exc
    except DB_ERRORS as exc:
        logger.exception("Mentor feedback DB error: call_id=%s", call_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис временно недоступен",
        ) from exc
