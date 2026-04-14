from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.trigger_rules import (
    TriggerActionCB,
    TriggerCohortTypeCB,
    TriggerCohortValueCB,
    TriggerDelayModeCB,
    TriggerPickCohortTypeCB,
    TriggerPickCohortValueCB,
    TriggerPickRoleCB,
    TriggerPickStateCB,
    TriggerPickUserCB,
    TriggerRecipientBackCB,
    TriggerRecipientPageCB,
    TriggerRecipientTypeCB,
    TriggerRegularityCB,
    TriggerRuleConfirmDeleteCB,
    TriggerRuleDeleteCB,
    TriggerRuleDetailCB,
    TriggerRuleEditFieldCB,
    TriggerRuleEditMenuCB,
    TriggerRuleToggleCB,
    TriggerScheduleModeCB,
    TriggerSurveyTemplateCB,
    TriggerTypeCB,
    TriggerUsersDoneCB,
)
from src.bot.keyboards.pagination import DEFAULT_PAGE_SIZE, build_paginated_keyboard
from src.models.role import RoleModel
from src.models.trigger import TriggerRule
from src.models.user import User


TRIGGER_TYPE_LABELS = {
    "meeting_created": "Создание встречи",
    "call_ended": "Завершение созвона",
    "periodic_cron": "По расписанию",
    "cohort_changed": "Смена когорты",
    "manual": "Ручной",
}

SCHEDULE_MODE_LABELS = {
    "cron": "Cron-выражение",
    "regularity": "Регулярность",
}

REGULARITY_LABELS = {
    "day": "Каждый день",
    "week": "Каждую неделю",
    "fortnight": "Раз в 2 недели",
    "month": "Раз в месяц",
}

ACTION_TYPE_LABELS = {
    "send_survey": "Отправить шаблон",
}

DELAY_MODE_LABELS = {
    "after_trigger": "После триггера",
    "before_scheduled": "До запланированного",
}

RECIPIENT_TYPE_LABELS = {
    "event_student": "Менти из события",
    "event_mentor": "Ментор из события",
    "event_user": "Пользователь события",
    "by_role": "По роли",
    "by_cohort": "По когорте",
    "by_state": "По статусу",
    "specific_users": "Конкретные пользователи",
    "direction_lead": "Руководитель направления",
}


def trigger_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in TRIGGER_TYPE_LABELS.items():
        builder.button(text=label, callback_data=TriggerTypeCB(value=value))
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def recipient_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in RECIPIENT_TYPE_LABELS.items():
        builder.button(text=label, callback_data=TriggerRecipientTypeCB(value=value))
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def survey_templates_keyboard(templates) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in templates:
        builder.button(
            text=t.title, callback_data=TriggerSurveyTemplateCB(template_id=t.id)
        )
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def rules_list_keyboard(
    rules: list[TriggerRule],
    page: int = 0,
    total_pages: int = 1,
    search_query: str | None = None,
) -> InlineKeyboardMarkup:
    item_buttons = [
        InlineKeyboardButton(
            text=f"Изменить #{page * DEFAULT_PAGE_SIZE + idx + 1}",
            callback_data=TriggerRuleDetailCB(rule_id=r.id).pack(),
        )
        for idx, r in enumerate(rules)
    ]
    return build_paginated_keyboard(
        menu="rules",
        page=page,
        total_pages=total_pages,
        item_buttons=item_buttons,
        columns=1,
        search_query=search_query,
        extra_rows=[
            [
                InlineKeyboardButton(
                    text="Создать правило",
                    callback_data=TriggerActionCB(action="create").pack(),
                )
            ]
        ],
        back_button=InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"),
    )


def rule_detail_keyboard(rule: TriggerRule) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "Выключить" if rule.is_active else "Включить"
    builder.button(text=toggle_text, callback_data=TriggerRuleToggleCB(rule_id=rule.id))
    builder.button(
        text="✏️ Изменить",
        callback_data=TriggerRuleEditMenuCB(rule_id=rule.id),
    )
    builder.button(text="Удалить", callback_data=TriggerRuleDeleteCB(rule_id=rule.id))
    builder.button(text="⬅️ Назад", callback_data="menu_triggers")
    builder.adjust(1)
    return builder.as_markup()


def delay_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in DELAY_MODE_LABELS.items():
        builder.button(text=label, callback_data=TriggerDelayModeCB(value=value))
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def rule_edit_menu_keyboard(rule: TriggerRule) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Название", callback_data=TriggerRuleEditFieldCB(field="nm"))
    builder.button(
        text="Тип триггера", callback_data=TriggerRuleEditFieldCB(field="tt")
    )
    builder.button(
        text="Шаблон (опрос/рассылка)",
        callback_data=TriggerRuleEditFieldCB(field="ac"),
    )
    builder.button(
        text="Тип получателей", callback_data=TriggerRuleEditFieldCB(field="rt")
    )
    if rule.recipient_type.value in (
        "by_role",
        "by_state",
        "by_cohort",
        "specific_users",
    ):
        builder.button(
            text="Настройки получателей",
            callback_data=TriggerRuleEditFieldCB(field="rc"),
        )
    builder.button(
        text="Задержка (сек)", callback_data=TriggerRuleEditFieldCB(field="dl")
    )
    builder.button(
        text="Режим задержки", callback_data=TriggerRuleEditFieldCB(field="dm")
    )
    if rule.trigger_type.value == "periodic_cron":
        builder.button(
            text="Cron-выражение",
            callback_data=TriggerRuleEditFieldCB(field="cr"),
        )
        builder.button(
            text="Регулярность",
            callback_data=TriggerRuleEditFieldCB(field="rg"),
        )
        builder.button(
            text="Время отправки",
            callback_data=TriggerRuleEditFieldCB(field="td"),
        )
    if rule.trigger_type.value == "cohort_changed":
        builder.button(
            text="Условия когорты",
            callback_data=TriggerRuleEditFieldCB(field="tc"),
        )
    builder.button(
        text="⬅️ Назад",
        callback_data=TriggerRuleDetailCB(rule_id=rule.id),
    )
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_rule_keyboard(rule_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Да, удалить",
        callback_data=TriggerRuleConfirmDeleteCB(rule_id=rule_id),
    )
    builder.button(text="❌ Отмена", callback_data="menu_triggers")
    builder.adjust(2)
    return builder.as_markup()


def schedule_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in SCHEDULE_MODE_LABELS.items():
        builder.button(text=label, callback_data=TriggerScheduleModeCB(value=value))
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def regularity_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in REGULARITY_LABELS.items():
        builder.button(text=label, callback_data=TriggerRegularityCB(value=value))
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def cohort_type_keyboard(types: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Любой тип", callback_data=TriggerCohortTypeCB(value="*"))
    for t in types:
        builder.button(text=t, callback_data=TriggerCohortTypeCB(value=t))
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def cohort_value_keyboard(values: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Любой", callback_data=TriggerCohortValueCB(value="*"))
    for v in values:
        builder.button(text=v, callback_data=TriggerCohortValueCB(value=v))
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def cohort_wildcard_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Любой", callback_data=TriggerCohortValueCB(value="*"))
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


# --- Recipient picker keyboards ---


def _tr_nav_row(kind: str, page: int, total_pages: int) -> list[InlineKeyboardButton]:
    if total_pages <= 1:
        return []
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="←",
                callback_data=TriggerRecipientPageCB(kind=kind, page=page - 1).pack(),
            )
        )
    else:
        buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                text="→",
                callback_data=TriggerRecipientPageCB(kind=kind, page=page + 1).pack(),
            )
        )
    else:
        buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    return buttons


def _tr_back_row(step: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TriggerRecipientBackCB(step=step).pack(),
        )
    ]


def _tr_cancel_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=TriggerActionCB(action="cancel").pack(),
        )
    ]


def trigger_roles_keyboard(
    roles: list[RoleModel], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    nav = _tr_nav_row("role", page, total_pages)
    if nav:
        kb.row(*nav)
    for role in roles:
        kb.row(
            InlineKeyboardButton(
                text=role.display_name or role.name,
                callback_data=TriggerPickRoleCB(role_id=role.id).pack(),
            )
        )
    kb.row(*_tr_back_row("type"))
    kb.row(*_tr_cancel_row())
    return kb.as_markup()


def trigger_states_keyboard(
    states: list[str], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    nav = _tr_nav_row("state", page, total_pages)
    if nav:
        kb.row(*nav)
    items_kb = InlineKeyboardBuilder()
    for value in states:
        items_kb.add(
            InlineKeyboardButton(
                text=value,
                callback_data=TriggerPickStateCB(value=value).pack(),
            )
        )
    items_kb.adjust(2)
    kb.attach(items_kb)
    kb.row(*_tr_back_row("type"))
    kb.row(*_tr_cancel_row())
    return kb.as_markup()


def trigger_rcohort_types_keyboard(
    types: list[str], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    nav = _tr_nav_row("ctype", page, total_pages)
    if nav:
        kb.row(*nav)
    for type_ in types:
        kb.row(
            InlineKeyboardButton(
                text=type_,
                callback_data=TriggerPickCohortTypeCB(type=type_).pack(),
            )
        )
    kb.row(*_tr_back_row("type"))
    kb.row(*_tr_cancel_row())
    return kb.as_markup()


def trigger_rcohort_values_keyboard(
    values: list[str], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    nav = _tr_nav_row("cval", page, total_pages)
    if nav:
        kb.row(*nav)
    for value in values:
        kb.row(
            InlineKeyboardButton(
                text=value,
                callback_data=TriggerPickCohortValueCB(value=value).pack(),
            )
        )
    kb.row(*_tr_back_row("ctype"))
    kb.row(*_tr_cancel_row())
    return kb.as_markup()


def trigger_users_keyboard(
    users: list[User],
    selected_ids: set[int],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    nav = _tr_nav_row("user", page, total_pages)
    if nav:
        kb.row(*nav)
    for user in users:
        handle = f"@{user.username}" if user.username else (user.name or "Без имени")
        prefix = "✅ " if user.telegram_id in selected_ids else ""
        kb.row(
            InlineKeyboardButton(
                text=f"{prefix}{handle}",
                callback_data=TriggerPickUserCB(telegram_id=user.telegram_id).pack(),
            )
        )
    kb.row(
        InlineKeyboardButton(
            text=f"Готово ({len(selected_ids)})",
            callback_data=TriggerUsersDoneCB().pack(),
        )
    )
    kb.row(*_tr_back_row("type"))
    kb.row(*_tr_cancel_row())
    return kb.as_markup()


def trigger_empty_recipient_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(*_tr_back_row("type"))
    kb.row(*_tr_cancel_row())
    return kb.as_markup()
