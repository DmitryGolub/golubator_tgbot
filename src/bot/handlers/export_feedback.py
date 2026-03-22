import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.services.feedback_export import FeedbackExportService
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

    await callback.message.edit_text("Экспорт фидбека запущен, подождите...")

    service = FeedbackExportService()
    try:
        result = await service.run_export(dry_run=False)
    except YandexSheetsConfigurationError:
        logger.exception("Feedback export configuration error")
        await callback.message.edit_text(
            "Экспорт не настроен: проверьте YANDEX_SHEETS_* переменные.",
            reply_markup=back_to_menu_keyboard(),
        )
        return
    except YandexSheetsUploadError:
        logger.exception("Feedback export upload failed")
        await callback.message.edit_text(
            "Не удалось загрузить файл в Яндекс Таблицу.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    if result.target is None:
        await callback.message.edit_text(
            "Внутренняя ошибка экспорта.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    logger.info(
        "Feedback export success: rows=%d file=%s",
        result.dataset.rows_count,
        result.target.file_path,
    )
    text = (
        f"Экспорт завершён.\n\n"
        f"Строк: <b>{result.dataset.rows_count}</b>\n"
        f"Файл: <b>{result.target.file_path}</b>\n"
        f"Лист: <b>{result.target.sheet_name}</b>"
    )

    try:
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
