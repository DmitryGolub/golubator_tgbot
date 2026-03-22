import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.core.config import settings
from src.services.feedback_export import FeedbackExportService
from src.services.ui_text import UiTextService
from src.services.yandex_sheets import (
    YandexSheetsConfigurationError,
    YandexSheetsUploadError,
)

logger = logging.getLogger(__name__)

router = Router(name="export_feedback")
router.callback_query.filter(PermissionFilter("export_feedback"))


@router.callback_query(F.data == "menu_export_feedback")
async def cb_export_feedback(callback: CallbackQuery):
    await callback.answer()

    if not settings.YANDEX_SHEETS_TOKEN:
        logger.warning("Feedback export skipped: YANDEX_SHEETS_TOKEN is not configured")
        text = await UiTextService.get("export.not_configured")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return

    loading = await UiTextService.get("export.running")
    await callback.message.edit_text(loading)

    service = FeedbackExportService()
    try:
        result = await service.run_export(dry_run=False)
    except YandexSheetsConfigurationError:
        logger.warning("Feedback export configuration error", exc_info=True)
        text = await UiTextService.get("export.not_configured")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return
    except YandexSheetsUploadError:
        logger.exception("Feedback export upload failed")
        text = await UiTextService.get("export.upload_error")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return

    if result.target is None:
        text = await UiTextService.get("export.internal_error")
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
        return

    logger.info(
        "Feedback export success: rows=%d file=%s",
        result.dataset.rows_count,
        result.target.file_path,
    )
    text = await UiTextService.get(
        "export.success",
        rows=str(result.dataset.rows_count),
        file=result.target.file_path,
        sheet=result.target.sheet_name,
    )

    try:
        await callback.message.edit_text(
            text, reply_markup=await back_to_menu_keyboard()
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
