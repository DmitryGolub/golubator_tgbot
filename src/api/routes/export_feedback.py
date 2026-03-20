import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.api.schemas.export_feedback import FeedbackExportResponse
from src.services.feedback_export import FeedbackExportService
from src.services.yandex_sheets import (
    YandexSheetsConfigurationError,
    YandexSheetsUploadError,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["export-feedback"])


@router.post("/export_feedback", response_model=FeedbackExportResponse)
async def export_feedback(
    date_from: Annotated[
        Optional[datetime],
        Query(description="Начало периода по scheduled_at/created_at (ISO 8601)"),
    ] = None,
    date_to: Annotated[
        Optional[datetime],
        Query(description="Конец периода по scheduled_at/created_at (ISO 8601)"),
    ] = None,
    dry_run: Annotated[
        bool,
        Query(description="Если true, данные в Яндекс Таблицу не отправляются"),
    ] = False,
) -> FeedbackExportResponse:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_from must be less than or equal to date_to",
        )

    service = FeedbackExportService()
    try:
        result = await service.run_export(
            date_from=date_from,
            date_to=date_to,
            dry_run=dry_run,
        )
    except YandexSheetsConfigurationError as exc:
        logger.exception("Feedback export configuration error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Экспорт не настроен: проверьте YANDEX_SHEETS_* переменные",
        ) from exc
    except YandexSheetsUploadError as exc:
        logger.exception("Feedback export upload failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось загрузить файл в Яндекс Таблицу",
        ) from exc

    if result.dry_run:
        return FeedbackExportResponse(
            status="dry_run",
            rows_count=result.dataset.rows_count,
            headers=list(result.dataset.headers),
            sample_rows=result.dataset.sample_rows(),
        )

    if result.target is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка экспорта: target is missing",
        )

    return FeedbackExportResponse(
        status="exported",
        rows_count=result.dataset.rows_count,
        target_file_path=result.target.file_path,
        sheet_name=result.target.sheet_name,
    )
