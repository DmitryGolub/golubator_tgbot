from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.trigger_rules import (
    TriggerActionCB,
    TriggerActionTypeCB,
    TriggerCohortTypeCB,
    TriggerCohortValueCB,
    TriggerRecipientTypeCB,
    TriggerRegularityCB,
    TriggerRuleConfirmDeleteCB,
    TriggerRuleDeleteCB,
    TriggerRuleDetailCB,
    TriggerRuleSendCB,
    TriggerRuleToggleCB,
    TriggerScheduleModeCB,
    TriggerSurveyTemplateCB,
    TriggerTypeCB,
)
from src.models.trigger import TriggerRule


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
    "send_notification": "Отправить уведомление",
    "send_survey": "Отправить опрос",
}

RECIPIENT_TYPE_LABELS = {
    "event_student": "Ученик из события",
    "event_mentor": "Ментор из события",
    "event_user": "Пользователь события",
    "by_role": "По роли",
    "by_cohort": "По когорте",
    "by_state": "По статусу",
    "specific_users": "Конкретные пользователи",
    "direction_lead": "Руководитель направления",
}


def trigger_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Создать правило", callback_data=TriggerActionCB(action="create")
    )
    builder.button(text="Список правил", callback_data=TriggerActionCB(action="list"))
    builder.button(
        text="Отправить вручную", callback_data=TriggerActionCB(action="manual_send")
    )
    builder.button(text="Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def trigger_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in TRIGGER_TYPE_LABELS.items():
        builder.button(text=label, callback_data=TriggerTypeCB(value=value))
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def action_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in ACTION_TYPE_LABELS.items():
        builder.button(text=label, callback_data=TriggerActionTypeCB(value=value))
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def recipient_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in RECIPIENT_TYPE_LABELS.items():
        builder.button(text=label, callback_data=TriggerRecipientTypeCB(value=value))
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def survey_templates_keyboard(templates) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in templates:
        builder.button(
            text=t.title, callback_data=TriggerSurveyTemplateCB(template_id=t.id)
        )
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def rules_list_keyboard(rules: list[TriggerRule]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in rules:
        status = "ON" if r.is_active else "OFF"
        trigger_label = TRIGGER_TYPE_LABELS.get(
            r.trigger_type.value, r.trigger_type.value
        )
        builder.button(
            text=f"[{status}] {r.name} ({trigger_label})",
            callback_data=TriggerRuleDetailCB(rule_id=r.id),
        )
    builder.button(text="Назад", callback_data="menu_triggers")
    builder.adjust(1)
    return builder.as_markup()


def rule_detail_keyboard(rule: TriggerRule) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "Выключить" if rule.is_active else "Включить"
    builder.button(text=toggle_text, callback_data=TriggerRuleToggleCB(rule_id=rule.id))
    builder.button(
        text="Отправить сейчас", callback_data=TriggerRuleSendCB(rule_id=rule.id)
    )
    builder.button(text="Удалить", callback_data=TriggerRuleDeleteCB(rule_id=rule.id))
    builder.button(text="Назад", callback_data=TriggerActionCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


def manual_send_rules_keyboard(rules: list[TriggerRule]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in rules:
        builder.button(text=r.name, callback_data=TriggerRuleSendCB(rule_id=r.id))
    builder.button(text="Назад", callback_data="menu_triggers")
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_rule_keyboard(rule_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Да, удалить",
        callback_data=TriggerRuleConfirmDeleteCB(rule_id=rule_id),
    )
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


def schedule_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in SCHEDULE_MODE_LABELS.items():
        builder.button(text=label, callback_data=TriggerScheduleModeCB(value=value))
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def regularity_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in REGULARITY_LABELS.items():
        builder.button(text=label, callback_data=TriggerRegularityCB(value=value))
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def cohort_type_keyboard(types: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Любой тип", callback_data=TriggerCohortTypeCB(value="*"))
    for t in types:
        builder.button(text=t, callback_data=TriggerCohortTypeCB(value=t))
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def cohort_value_keyboard(values: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Любой", callback_data=TriggerCohortValueCB(value="*"))
    for v in values:
        builder.button(text=v, callback_data=TriggerCohortValueCB(value=v))
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def cohort_wildcard_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Любой", callback_data=TriggerCohortValueCB(value="*"))
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data=TriggerActionCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()
