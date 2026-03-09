import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.exc import DataError, OperationalError, ProgrammingError, SQLAlchemyError

from src.api.schemas.mentor import MentorStatsResponse
from src.dao.mentor_stats import MentorStatsDAO

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mentors", tags=["mentors"])

DB_ERRORS: tuple[type[BaseException], ...] = (
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)

try:
    import asyncpg
except ImportError:
    asyncpg = None
else:
    DB_ERRORS = DB_ERRORS + (asyncpg.PostgresError,)


@router.get("/{mentor_id}/stats", response_model=MentorStatsResponse)
async def get_mentor_stats(
    mentor_id: int,
    date_from: Annotated[
        Optional[datetime],
        Query(description="Начало периода (ISO 8601)"),
    ] = None,
    date_to: Annotated[
        Optional[datetime],
        Query(description="Конец периода (ISO 8601)"),
    ] = None,
) -> MentorStatsResponse:
    """Агрегированная статистика по ментору."""
    try:
        stats = await MentorStatsDAO.get_stats(
            mentor_id=mentor_id,
            date_from=date_from,
            date_to=date_to,
        )
    except DataError as exc:
        logger.info("Invalid mentor_id value: mentor_id=%s", mentor_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректный mentor_id",
        ) from exc
    except DB_ERRORS as exc:
        logger.exception("Mentor stats DB error: mentor_id=%s", mentor_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис временно недоступен",
        ) from exc

    return MentorStatsResponse(**stats)
