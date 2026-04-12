from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from src.services.ui_text import UiTextService

# Permission -> (ui_text key, callback_data) mapping for menu buttons
_ADMIN_BUTTONS = [
    ("manage_users", "menu.btn.users", "menu_users"),
    ("manage_cohorts", "menu.btn.cohorts", "menu_cohorts"),
    ("manage_surveys", "menu.btn.surveys", "menu_surveys"),
    ("manage_triggers", "menu.btn.triggers", "menu_triggers"),
    ("manage_roles", "menu.btn.roles", "menu_roles"),
    ("manage_users", "menu.btn.mentor_stats", "admin_mentor_stats"),
]

_MENTOR_BUTTONS = [
    ("view_students", "menu.btn.students", "mentor_students_menu"),
    ("manage_meetings", "menu.btn.meetings", "mentor_meetings_menu"),
]

_LEAD_BUTTONS = [
    (
        "view_direction_students",
        "menu.btn.direction_students",
        "lead_direction_students",
    ),
]

_JOB_SEARCH_BUTTONS = [
    (
        "view_job_search_reports",
        "menu.btn.job_search_reports",
        "job_search_report_menu",
    ),
]

_EDUCATION_BUTTONS = [
    (
        "view_education_feedback",
        "menu.btn.education_feedback",
        "education_feedback_menu",
    ),
]

_STUDENT_BUTTONS = [
    ("propose_meetings", "menu.btn.propose_meeting", "student_propose_meeting"),
]

_REFERRAL_BUTTONS = [
    ("view_referral_link", "menu.btn.referral_link", "menu_referral_link"),
]

_CHANNEL_LINK_BUTTONS = [
    ("manage_channel_links", "menu.btn.channel_links", "menu_channel_links"),
]


async def menu_keyboard(
    permissions: set[str],
    *,
    has_mentor: bool = True,
    has_directions: bool = True,
) -> InlineKeyboardMarkup:
    needed_keys: list[str] = []
    buttons_spec: list[tuple[str, str]] = []  # (ui_text_key, callback_data)

    for perm, key, cb in _ADMIN_BUTTONS:
        if perm in permissions:
            needed_keys.append(key)
            buttons_spec.append((key, cb))

    for perm, key, cb in _MENTOR_BUTTONS:
        if perm in permissions:
            needed_keys.append(key)
            buttons_spec.append((key, cb))

    for perm, key, cb in _LEAD_BUTTONS:
        if perm in permissions:
            if perm == "view_direction_students" and not has_directions:
                continue
            needed_keys.append(key)
            buttons_spec.append((key, cb))

    for perm, key, cb in _JOB_SEARCH_BUTTONS:
        if perm in permissions:
            needed_keys.append(key)
            buttons_spec.append((key, cb))

    for perm, key, cb in _EDUCATION_BUTTONS:
        if perm in permissions:
            needed_keys.append(key)
            buttons_spec.append((key, cb))

    for perm, key, cb in _STUDENT_BUTTONS:
        if perm in permissions:
            if perm == "propose_meetings" and not has_mentor:
                continue
            needed_keys.append(key)
            buttons_spec.append((key, cb))

    for perm, key, cb in _REFERRAL_BUTTONS:
        if perm in permissions:
            needed_keys.append(key)
            buttons_spec.append((key, cb))

    for perm, key, cb in _CHANNEL_LINK_BUTTONS:
        if perm in permissions:
            needed_keys.append(key)
            buttons_spec.append((key, cb))

    if "view_own_info" in permissions and "view_students" in permissions:
        needed_keys.append("menu.btn.my_info")
        buttons_spec.append(("menu.btn.my_info", "mentor_me_info"))

    if "view_own_meetings" in permissions and "manage_meetings" not in permissions:
        needed_keys.append("menu.btn.my_meetings")
        buttons_spec.append(("menu.btn.my_meetings", "student_meetings"))

    if "view_own_info" in permissions and "view_students" not in permissions:
        needed_keys.append("menu.btn.my_info_student")
        buttons_spec.append(("menu.btn.my_info_student", "student_me_info"))

    if "view_own_info" in permissions:
        needed_keys.append("menu.btn.feedback_report")
        buttons_spec.append(("menu.btn.feedback_report", "feedback_report_menu"))

    texts = await UiTextService.get_many(needed_keys) if needed_keys else {}

    kb = InlineKeyboardBuilder()
    for key, cb in buttons_spec:
        kb.button(text=texts.get(key, key), callback_data=cb)

    kb.adjust(1)
    return kb.as_markup()


async def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    back_text = await UiTextService.get("menu.back")
    kb = InlineKeyboardBuilder()
    kb.button(text=back_text, callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()
