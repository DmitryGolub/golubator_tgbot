from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.education_feedback import education_period_keyboard
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.services.education_feedback import EducationFeedbackService
from src.services.ui_text import UiTextService

router = Router(name="education_feedback")
router.callback_query.filter(PermissionFilter("view_education_feedback"))


@router.callback_query(F.data == "education_feedback_menu")
async def cb_education_menu(callback: CallbackQuery):
    await callback.answer()
    text = await UiTextService.get("education.choose_period")
    await callback.message.edit_text(text, reply_markup=education_period_keyboard())


@router.callback_query(F.data.startswith("education_period:"))
async def cb_education_period(callback: CallbackQuery):
    await callback.answer()
    period = callback.data.split(":", 1)[1]

    now = datetime.now(timezone.utc)
    date_from = None
    if period == "week":
        date_from = now - timedelta(weeks=1)
    elif period == "month":
        date_from = now - timedelta(days=30)

    text = await EducationFeedbackService.get_summary(date_from=date_from)
    if not text:
        text = await UiTextService.get("education.no_data")

    await callback.message.edit_text(text, reply_markup=await back_to_menu_keyboard())
