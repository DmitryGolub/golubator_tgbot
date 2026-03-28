from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.job_search_report import job_search_period_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.services.job_search_report import JobSearchReportService
from src.services.ui_text import UiTextService

router = Router(name="job_search_report")
router.callback_query.filter(PermissionFilter("view_job_search_reports"))


@router.callback_query(F.data == "job_search_report_menu")
async def cb_job_search_menu(callback: CallbackQuery):
    await callback.answer()
    text = await UiTextService.get("job_search.choose_period")
    await callback.message.edit_text(text, reply_markup=job_search_period_keyboard())


@router.callback_query(F.data.startswith("job_search_period:"))
async def cb_job_search_period(callback: CallbackQuery):
    await callback.answer()
    period = callback.data.split(":", 1)[1]

    now = datetime.now(timezone.utc)
    date_from = None
    if period == "week":
        date_from = now - timedelta(weeks=1)
    elif period == "month":
        date_from = now - timedelta(days=30)

    text = await JobSearchReportService.get_summary(date_from=date_from)
    if not text:
        text = await UiTextService.get("job_search.no_data")

    await callback.message.edit_text(text, reply_markup=await back_to_menu_keyboard())
