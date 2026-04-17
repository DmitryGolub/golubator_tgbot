from aiogram.filters.callback_data import CallbackData


class FeedbackTypeCB(CallbackData, prefix="fb_type"):
    value: str  # "problem" | "bug"


class FeedbackRecipientCB(CallbackData, prefix="fb_rcpt"):
    role: str  # "admin" | "direction_lead" | "education_lead" | "job_search_lead"
