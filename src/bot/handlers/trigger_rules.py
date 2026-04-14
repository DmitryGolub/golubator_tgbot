import logging
from datetime import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext

from src.bot.callbacks.pagination import PageNavCB
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
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.pagination import get_page_slice
from src.bot.keyboards.trigger_rules import (
    ACTION_TYPE_LABELS,
    DELAY_MODE_LABELS,
    RECIPIENT_TYPE_LABELS,
    REGULARITY_LABELS,
    TRIGGER_TYPE_LABELS,
    cancel_keyboard,
    cohort_type_keyboard,
    cohort_value_keyboard,
    cohort_wildcard_keyboard,
    confirm_delete_rule_keyboard,
    delay_mode_keyboard,
    recipient_type_keyboard,
    regularity_keyboard,
    rule_detail_keyboard,
    rule_edit_menu_keyboard,
    rules_list_keyboard,
    schedule_mode_keyboard,
    survey_templates_keyboard,
    trigger_empty_recipient_keyboard,
    trigger_rcohort_types_keyboard,
    trigger_rcohort_values_keyboard,
    trigger_roles_keyboard,
    trigger_states_keyboard,
    trigger_type_keyboard,
    trigger_users_keyboard,
)
from src.bot.pagination_search import filter_items
from src.bot.states.trigger_rules import TriggerRuleBuilderFSM, TriggerRuleEditFSM
from src.bot.utils import safe_edit_text
from src.dao.cohort import CohortDAO
from src.dao.role import RoleDAO
from src.dao.trigger_rule import TriggerRuleDAO
from src.dao.user import UserDAO
from src.models.trigger import (
    DelayMode,
    RecipientType,
    TriggerRule,
    TriggerType,
)
from src.models.enums import Regularity
from src.services.survey_template import SurveyTemplateService
from src.services.ui_text import UiTextService
from src.utils.escape import e

USERS_PAGE_SIZE = 6

logger = logging.getLogger(__name__)

router = Router(name="trigger_rules")
router.message.filter(PermissionFilter("manage_triggers"))
router.callback_query.filter(PermissionFilter("manage_triggers"))


# --- Menu ---


@router.callback_query(F.data == "menu_triggers")
async def cb_triggers_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("rules")
    text, markup = await _build_rules_list_page(page=0, search_query=sq)
    await safe_edit_text(callback, text, reply_markup=markup)


# --- List ---


def _format_delay(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    if seconds < 3600:
        return f"{seconds // 60} мин"
    return f"{seconds // 3600} ч"


async def _build_rules_list_page(
    page: int = 0, search_query: str | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    rules = await TriggerRuleDAO.get_all()
    filtered = filter_items(rules, search_query, "rules") if search_query else rules
    page_items, total_pages = get_page_slice(filtered, page)

    if not filtered:
        return "Нет правил.", rules_list_keyboard([], page=0, total_pages=1)

    lines = ["<b>Правила:</b>\n"]
    for idx, r in enumerate(page_items):
        global_num = page * 6 + idx + 1
        status = "ON" if r.is_active else "OFF"
        trigger_label = TRIGGER_TYPE_LABELS.get(
            r.trigger_type.value, r.trigger_type.value
        )
        action_label = ACTION_TYPE_LABELS.get(r.action_type.value, r.action_type.value)
        recipient_label = RECIPIENT_TYPE_LABELS.get(
            r.recipient_type.value, r.recipient_type.value
        )
        entry = (
            f"{global_num}. [{status}] {e(r.name)}\n"
            f"   Триггер: {e(trigger_label)}\n"
            f"   Действие: {e(action_label)}\n"
            f"   Получатели: {e(recipient_label)}"
        )
        if r.delay_seconds:
            entry += f"\n   Задержка: {_format_delay(r.delay_seconds)}"
        if r.trigger_type.value == "periodic_cron" and r.cron_expression:
            entry += f"\n   Расписание: {e(r.cron_expression)}"
        lines.append(entry)

    text = "\n\n".join(lines)
    markup = rules_list_keyboard(
        list(page_items),
        page=page,
        total_pages=total_pages,
        search_query=search_query,
    )
    return text, markup


@router.callback_query(PageNavCB.filter(F.menu == "rules"))
async def cb_rules_page(
    callback: CallbackQuery, callback_data: PageNavCB, state: FSMContext
):
    data = await state.get_data()
    sq = (data.get("_pagination_search") or {}).get("rules")
    text, markup = await _build_rules_list_page(
        page=callback_data.page, search_query=sq
    )
    await safe_edit_text(callback, text, reply_markup=markup)
    await callback.answer()


async def _format_recipient_config(rule: TriggerRule) -> str | None:
    cfg = rule.recipient_config
    if not cfg:
        return None
    rt = rule.recipient_type.value
    if rt == "by_role":
        role_name = cfg.get("role_name")
        if not role_name:
            return None
        role = await RoleDAO.find_one_or_none(name=role_name)
        label = (role.display_name or role.name) if role else role_name
        return f"Роль: {label}"
    if rt == "by_state":
        value = cfg.get("state")
        return f"Статус: {value}" if value else None
    if rt == "by_cohort":
        ctype = cfg.get("cohort_type")
        cvalue = cfg.get("cohort_value")
        if ctype and cvalue:
            return f"Когорта: {ctype} — {cvalue}"
        if cvalue:
            return f"Когорта: {cvalue}"
        return None
    if rt == "specific_users":
        user_ids = cfg.get("user_ids") or []
        if not user_ids:
            return None
        names: list[str] = []
        for uid in user_ids:
            user = await UserDAO.find_one_or_none(telegram_id=uid)
            if user and user.name:
                names.append(user.name)
            elif user and user.username:
                names.append(f"@{user.username}")
            else:
                names.append("Неизвестный пользователь")
        return "Пользователи: " + ", ".join(names)
    return None


async def _format_rule_detail(
    rule: TriggerRule,
) -> tuple[str, InlineKeyboardMarkup]:
    trigger_label = TRIGGER_TYPE_LABELS.get(
        rule.trigger_type.value, rule.trigger_type.value
    )
    action_label = ACTION_TYPE_LABELS.get(
        rule.action_type.value, rule.action_type.value
    )
    recipient_label = RECIPIENT_TYPE_LABELS.get(
        rule.recipient_type.value, rule.recipient_type.value
    )
    delay_mode_label = DELAY_MODE_LABELS.get(
        rule.delay_mode.value, rule.delay_mode.value
    )
    status = "Активно" if rule.is_active else "Отключено"

    text = (
        f"<b>{e(rule.name)}</b>\n\n"
        f"Триггер: {e(trigger_label)}\n"
        f"Действие: {e(action_label)}\n"
        f"Получатели: {e(recipient_label)}\n"
        f"Задержка: {rule.delay_seconds} сек ({e(delay_mode_label)})\n"
        f"Статус: {status}"
    )

    if rule.action_config is None:
        text += "\nСодержимое действия: <i>не задано</i>"

    if rule.cron_expression:
        text += f"\nCron: <code>{e(rule.cron_expression)}</code>"
    if rule.regularity:
        regularity_label = REGULARITY_LABELS.get(
            rule.regularity.value, rule.regularity.value
        )
        text += f"\nРегулярность: {e(regularity_label)}"
    if rule.time_of_day:
        text += f"\nВремя: {rule.time_of_day.strftime('%H:%M')}"

    recipient_info = await _format_recipient_config(rule)
    if recipient_info:
        text += f"\n{e(recipient_info)}"

    if rule.trigger_config:
        cfg = rule.trigger_config
        ct = cfg.get("cohort_type", "*")
        fv = cfg.get("from_value", "*")
        tv = cfg.get("to_value", "*")
        ct_label = "Любой" if ct == "*" else ct
        fv_label = "Любой" if fv == "*" else fv
        tv_label = "Любой" if tv == "*" else tv
        text += (
            f"\n\nУсловия когорты:\n"
            f"  Тип: {e(ct_label)}\n"
            f"  Из: {e(fv_label)}\n"
            f"  В: {e(tv_label)}"
        )

    return text, rule_detail_keyboard(rule)


@router.callback_query(TriggerRuleDetailCB.filter())
async def cb_rule_detail(
    callback: CallbackQuery,
    callback_data: TriggerRuleDetailCB,
    state: FSMContext,
):
    await state.clear()
    rule = await TriggerRuleDAO.get_by_id(callback_data.rule_id)
    if not rule:
        await callback.answer(await UiTextService.get("trigger.rule_not_found"))
        return
    text, markup = await _format_rule_detail(rule)
    await callback.answer()
    await safe_edit_text(callback, text, reply_markup=markup)


@router.callback_query(TriggerRuleToggleCB.filter())
async def cb_toggle_rule(callback: CallbackQuery, callback_data: TriggerRuleToggleCB):
    rule = await TriggerRuleDAO.get_by_id(callback_data.rule_id)
    if not rule:
        await callback.answer(await UiTextService.get("trigger.rule_not_found"))
        return
    rule = await TriggerRuleDAO.set_active(rule.id, not rule.is_active)
    status = "включено" if rule.is_active else "выключено"
    await callback.answer(f"Правило {status}")
    await safe_edit_text(
        callback,
        f"Правило <b>{e(rule.name)}</b> — {status}.",
        reply_markup=rule_detail_keyboard(rule),
    )


@router.callback_query(TriggerRuleDeleteCB.filter())
async def cb_delete_rule_confirm(
    callback: CallbackQuery, callback_data: TriggerRuleDeleteCB
):
    await callback.answer()
    rule = await TriggerRuleDAO.get_by_id(callback_data.rule_id)
    if not rule:
        text, markup = await _build_rules_list_page(page=0)
        await safe_edit_text(callback, text, reply_markup=markup)
        return
    await safe_edit_text(
        callback,
        f"Удалить правило <b>{e(rule.name)}</b>?",
        reply_markup=confirm_delete_rule_keyboard(rule.id),
    )


@router.callback_query(TriggerRuleConfirmDeleteCB.filter())
async def cb_delete_rule(
    callback: CallbackQuery, callback_data: TriggerRuleConfirmDeleteCB
):
    deleted = await TriggerRuleDAO.delete(callback_data.rule_id)
    if not deleted:
        await callback.answer(await UiTextService.get("trigger.rule_not_found"))
        return
    await callback.answer(await UiTextService.get("trigger.deleted"))
    rules = await TriggerRuleDAO.get_all()
    if rules:
        text, markup = await _build_rules_list_page(page=0)
        await safe_edit_text(callback, text, reply_markup=markup)
    else:
        text, markup = await _build_rules_list_page(page=0)
        await safe_edit_text(callback, text, reply_markup=markup)


# --- Create rule FSM ---


@router.callback_query(TriggerActionCB.filter(F.action == "create"))
async def cb_start_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(TriggerRuleBuilderFSM.entering_name)
    await callback.answer()
    await safe_edit_text(
        callback, "Введите название правила:", reply_markup=cancel_keyboard()
    )


@router.message(TriggerRuleBuilderFSM.entering_name)
async def msg_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым:")
        return
    await state.update_data(name=name)
    await state.set_state(TriggerRuleBuilderFSM.choosing_trigger_type)
    await message.answer("Выберите тип триггера:", reply_markup=trigger_type_keyboard())


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_trigger_type, TriggerTypeCB.filter()
)
async def cb_trigger_type(
    callback: CallbackQuery, callback_data: TriggerTypeCB, state: FSMContext
):
    await state.update_data(trigger_type=callback_data.value)
    await callback.answer()

    if callback_data.value == "periodic_cron":
        await state.set_state(TriggerRuleBuilderFSM.choosing_schedule_mode)
        await safe_edit_text(
            callback,
            "Выберите способ задания расписания:",
            reply_markup=schedule_mode_keyboard(),
        )
    elif callback_data.value == "cohort_changed":
        from src.dao.cohort import CohortDAO

        types = await CohortDAO.get_distinct_types()
        await state.set_state(TriggerRuleBuilderFSM.choosing_cohort_type)
        await safe_edit_text(
            callback,
            "Выберите тип когорты для отслеживания:",
            reply_markup=cohort_type_keyboard(types),
        )
    else:
        await _prompt_survey_templates(callback, state)


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_schedule_mode, TriggerScheduleModeCB.filter()
)
async def cb_schedule_mode(
    callback: CallbackQuery, callback_data: TriggerScheduleModeCB, state: FSMContext
):
    await callback.answer()
    if callback_data.value == "cron":
        await state.set_state(TriggerRuleBuilderFSM.entering_cron_expression)
        await safe_edit_text(
            callback,
            "Введите cron-выражение (5 полей):\n"
            "<code>минуты часы день_месяца месяц день_недели</code>\n\n"
            "Примеры:\n"
            "<code>0 9 * * 1</code> — каждый понедельник в 09:00 UTC\n"
            "<code>*/30 * * * *</code> — каждые 30 минут\n"
            "<code>0 10 1 * *</code> — 1-го числа каждого месяца в 10:00 UTC",
            reply_markup=cancel_keyboard(),
        )
    else:
        await state.set_state(TriggerRuleBuilderFSM.choosing_regularity)
        await safe_edit_text(
            callback, "Выберите регулярность:", reply_markup=regularity_keyboard()
        )


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_cohort_type, TriggerCohortTypeCB.filter()
)
async def cb_cohort_type(
    callback: CallbackQuery, callback_data: TriggerCohortTypeCB, state: FSMContext
):
    cohort_type = callback_data.value
    await state.update_data(cohort_config_type=cohort_type)
    await callback.answer()

    if cohort_type == "*":
        await state.set_state(TriggerRuleBuilderFSM.choosing_cohort_from)
        await safe_edit_text(
            callback,
            "Начальное значение (from):",
            reply_markup=cohort_wildcard_keyboard(),
        )
    else:
        values = await CohortDAO.get_distinct_values(cohort_type)
        await state.set_state(TriggerRuleBuilderFSM.choosing_cohort_from)
        await safe_edit_text(
            callback,
            "Выберите начальное значение (from):",
            reply_markup=cohort_value_keyboard(values),
        )


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_cohort_from, TriggerCohortValueCB.filter()
)
async def cb_cohort_from(
    callback: CallbackQuery, callback_data: TriggerCohortValueCB, state: FSMContext
):
    from_value = callback_data.value
    await state.update_data(cohort_config_from=from_value)
    await callback.answer()

    data = await state.get_data()
    cohort_type = data.get("cohort_config_type", "*")

    if cohort_type == "*":
        await state.set_state(TriggerRuleBuilderFSM.choosing_cohort_to)
        await safe_edit_text(
            callback, "Конечное значение (to):", reply_markup=cohort_wildcard_keyboard()
        )
    else:
        values = await CohortDAO.get_distinct_values(cohort_type)
        await state.set_state(TriggerRuleBuilderFSM.choosing_cohort_to)
        await safe_edit_text(
            callback,
            "Выберите конечное значение (to):",
            reply_markup=cohort_value_keyboard(values),
        )


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_cohort_to, TriggerCohortValueCB.filter()
)
async def cb_cohort_to(
    callback: CallbackQuery, callback_data: TriggerCohortValueCB, state: FSMContext
):
    to_value = callback_data.value
    data = await state.get_data()
    trigger_config = {
        "cohort_type": data.get("cohort_config_type", "*"),
        "from_value": data.get("cohort_config_from", "*"),
        "to_value": to_value,
    }
    await state.update_data(trigger_config=trigger_config)
    await callback.answer()

    await _prompt_survey_templates(callback, state)


_CRON_RANGES = [
    (0, 59),
    (0, 23),
    (1, 31),
    (1, 12),
    (0, 6),
]  # min, hour, dom, month, dow


def _validate_cron(expr: str) -> str | None:
    """Return error message if cron expression is invalid, else None."""
    parts = expr.split()
    if len(parts) != 5:
        return "Cron-выражение должно содержать ровно 5 полей."
    for part, (lo, hi) in zip(parts, _CRON_RANGES):
        if part == "*":
            continue
        if part.startswith("*/"):
            try:
                n = int(part[2:])
            except ValueError:
                return f"Невалидное поле: {part}"
            if n < 1 or n > hi:
                return f"Шаг {part} вне допустимого диапазона 1–{hi}."
            continue
        for sub in part.split(","):
            if "-" in sub:
                pieces = sub.split("-", 1)
                if len(pieces) != 2:
                    return f"Невалидный диапазон: {sub}"
                try:
                    a, b = int(pieces[0]), int(pieces[1])
                except ValueError:
                    return f"Невалидный диапазон: {sub}"
                if not (lo <= a <= hi) or not (lo <= b <= hi):
                    return f"Диапазон {sub} вне допустимых значений {lo}–{hi}."
            else:
                try:
                    val = int(sub)
                except ValueError:
                    return f"Невалидное значение: {sub}"
                if not (lo <= val <= hi):
                    return f"Значение {val} вне допустимого диапазона {lo}–{hi}."
    return None


async def _prompt_survey_templates_msg(message: Message, state: FSMContext) -> None:
    service = SurveyTemplateService()
    templates = await service.list_active()
    if not templates:
        await state.clear()
        await message.answer(
            "Нет активных шаблонов. Сначала создайте опрос или рассылку."
        )
        return
    await state.set_state(TriggerRuleBuilderFSM.choosing_survey_template)
    await message.answer(
        "Выберите шаблон (опрос или рассылку):",
        reply_markup=survey_templates_keyboard(templates),
    )


@router.message(TriggerRuleBuilderFSM.entering_cron_expression)
async def msg_cron_expression(message: Message, state: FSMContext):
    expr = message.text.strip()
    error = _validate_cron(expr)
    if error:
        await message.answer(f"{error} Попробуйте снова:")
        return
    await state.update_data(cron_expression=expr)
    await _prompt_survey_templates_msg(message, state)


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_regularity, TriggerRegularityCB.filter()
)
async def cb_regularity(
    callback: CallbackQuery, callback_data: TriggerRegularityCB, state: FSMContext
):
    await state.update_data(regularity=callback_data.value)
    await state.set_state(TriggerRuleBuilderFSM.entering_time_of_day)
    await callback.answer()
    await safe_edit_text(
        callback, "Введите время отправки (HH:MM, UTC):", reply_markup=cancel_keyboard()
    )


def _parse_time_of_day(text: str) -> tuple[time | None, str | None]:
    parts = text.strip().split(":")
    if len(parts) != 2:
        return None, "Формат: HH:MM (например, 09:30). Попробуйте снова:"
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None, "Формат: HH:MM (например, 09:30). Попробуйте снова:"
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None, "Часы: 0-23, минуты: 0-59. Попробуйте снова:"
    return time(h, m), None


@router.message(TriggerRuleBuilderFSM.entering_time_of_day)
async def msg_time_of_day(message: Message, state: FSMContext):
    t, err = _parse_time_of_day(message.text or "")
    if err:
        await message.answer(err)
        return
    await state.update_data(time_of_day=f"{t.hour:02d}:{t.minute:02d}")
    await _prompt_survey_templates_msg(message, state)


async def _prompt_survey_templates(callback: CallbackQuery, state: FSMContext) -> None:
    service = SurveyTemplateService()
    templates = await service.list_active()
    if not templates:
        await safe_edit_text(
            callback,
            "Нет активных шаблонов. Сначала создайте опрос или рассылку.",
        )
        await state.clear()
        return
    await state.set_state(TriggerRuleBuilderFSM.choosing_survey_template)
    await safe_edit_text(
        callback,
        "Выберите шаблон (опрос или рассылку):",
        reply_markup=survey_templates_keyboard(templates),
    )


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_survey_template, TriggerSurveyTemplateCB.filter()
)
async def cb_choose_template(
    callback: CallbackQuery, callback_data: TriggerSurveyTemplateCB, state: FSMContext
):
    service = SurveyTemplateService()
    template = await service.get(callback_data.template_id)
    action_config = {
        "survey_template_id": template.id,
        "survey_title": template.title,
    }
    from src.models.survey_template import TemplateKind

    if template.kind == TemplateKind.broadcast:
        action_config["escalatable"] = False
    await state.update_data(
        action_type="send_survey",
        action_config=action_config,
    )
    await state.set_state(TriggerRuleBuilderFSM.choosing_recipient_type)
    await callback.answer()
    await safe_edit_text(
        callback, "Выберите тип получателей:", reply_markup=recipient_type_keyboard()
    )


async def _show_recipient_picker(
    callback: CallbackQuery, rt: str, state: FSMContext
) -> None:
    if rt == "by_role":
        roles = list(await RoleDAO.get_all())
        if not roles:
            await safe_edit_text(
                callback,
                "В базе нет ни одной роли.",
                reply_markup=trigger_empty_recipient_keyboard(),
            )
            return
        page_items, total_pages = get_page_slice(roles, 0)
        await safe_edit_text(
            callback,
            "Выберите роль:",
            reply_markup=trigger_roles_keyboard(list(page_items), 0, total_pages),
        )
    elif rt == "by_state":
        states = await CohortDAO.get_distinct_values("Status")
        if not states:
            await safe_edit_text(
                callback,
                "В базе нет ни одного статуса.",
                reply_markup=trigger_empty_recipient_keyboard(),
            )
            return
        page_items, total_pages = get_page_slice(states, 0)
        await safe_edit_text(
            callback,
            "Выберите статус:",
            reply_markup=trigger_states_keyboard(list(page_items), 0, total_pages),
        )
    elif rt == "by_cohort":
        types = await CohortDAO.get_distinct_types()
        if not types:
            await safe_edit_text(
                callback,
                "В базе нет ни одной когорты.",
                reply_markup=trigger_empty_recipient_keyboard(),
            )
            return
        page_items, total_pages = get_page_slice(types, 0)
        await safe_edit_text(
            callback,
            "Выберите тип когорты:",
            reply_markup=trigger_rcohort_types_keyboard(
                list(page_items), 0, total_pages
            ),
        )
    elif rt == "specific_users":
        users, total_pages = await UserDAO.get_paginated(
            page=0, page_size=USERS_PAGE_SIZE, exclude_placeholders=True
        )
        if not users and total_pages <= 1:
            await safe_edit_text(
                callback,
                "Нет доступных пользователей.",
                reply_markup=trigger_empty_recipient_keyboard(),
            )
            return
        await state.update_data(users_selected=[], users_page=0)
        await safe_edit_text(
            callback,
            "Выберите получателей (нажимайте, чтобы отметить/снять), затем «Готово»:",
            reply_markup=trigger_users_keyboard(users, set(), 0, total_pages),
        )


async def _after_recipient_config(
    callback: CallbackQuery, state: FSMContext, summary: str
) -> None:
    data = await state.get_data()
    if data.get("edit_rule_id"):
        # Edit flow: finish immediately
        config = data.get("recipient_config")
        await _finish_edit(callback, state, recipient_config=config)
        return
    # Create flow: proceed to delay
    await state.set_state(TriggerRuleBuilderFSM.setting_delay)
    await safe_edit_text(
        callback,
        f"Получатели сохранены: {e(summary)}\n\n"
        "Задержка отправки в секундах (0 = немедленно):",
        reply_markup=cancel_keyboard(),
    )


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_recipient_type, TriggerRecipientTypeCB.filter()
)
async def cb_recipient_type(
    callback: CallbackQuery, callback_data: TriggerRecipientTypeCB, state: FSMContext
):
    rt = callback_data.value
    await state.update_data(recipient_type=rt, recipient_config=None)
    await callback.answer()

    if rt in ("by_role", "by_state", "by_cohort", "specific_users"):
        await state.set_state(TriggerRuleBuilderFSM.configuring_recipients)
        await _show_recipient_picker(callback, rt, state)
    else:
        await state.set_state(TriggerRuleBuilderFSM.setting_delay)
        await safe_edit_text(
            callback,
            "Задержка отправки в секундах (0 = немедленно):",
            reply_markup=cancel_keyboard(),
        )


# --- Recipient picker handlers (shared between create and edit flows) ---


def _recipient_picker_states():
    return (
        TriggerRuleBuilderFSM.configuring_recipients,
        TriggerRuleEditFSM.editing_recipient_config,
    )


@router.callback_query(TriggerPickRoleCB.filter())
async def cb_pick_role(
    callback: CallbackQuery, callback_data: TriggerPickRoleCB, state: FSMContext
):
    current = await state.get_state()
    if current not in {s.state for s in _recipient_picker_states()}:
        return
    await callback.answer()
    role = await RoleDAO.find_one_or_none(id=callback_data.role_id)
    if role is None:
        await safe_edit_text(callback, "Роль не найдена.")
        return
    await state.update_data(recipient_config={"role_name": role.name})
    await _after_recipient_config(callback, state, role.display_name or role.name)


@router.callback_query(TriggerPickStateCB.filter())
async def cb_pick_state(
    callback: CallbackQuery, callback_data: TriggerPickStateCB, state: FSMContext
):
    current = await state.get_state()
    if current not in {s.state for s in _recipient_picker_states()}:
        return
    await callback.answer()
    value = callback_data.value
    await state.update_data(recipient_config={"state": value})
    await _after_recipient_config(callback, state, value)


@router.callback_query(TriggerPickCohortTypeCB.filter())
async def cb_pick_cohort_type(
    callback: CallbackQuery,
    callback_data: TriggerPickCohortTypeCB,
    state: FSMContext,
):
    current = await state.get_state()
    if current not in {s.state for s in _recipient_picker_states()}:
        return
    await callback.answer()
    cohort_type = callback_data.type
    values = await CohortDAO.get_distinct_values(cohort_type)
    if not values:
        await safe_edit_text(
            callback,
            f"В когорте «{e(cohort_type)}» нет значений.",
            reply_markup=trigger_empty_recipient_keyboard(),
        )
        return
    await state.update_data(recipient_cohort_type_pending=cohort_type)
    page_items, total_pages = get_page_slice(values, 0)
    await safe_edit_text(
        callback,
        f"Выберите значение когорты «{e(cohort_type)}»:",
        reply_markup=trigger_rcohort_values_keyboard(list(page_items), 0, total_pages),
    )


@router.callback_query(TriggerPickCohortValueCB.filter())
async def cb_pick_cohort_value(
    callback: CallbackQuery,
    callback_data: TriggerPickCohortValueCB,
    state: FSMContext,
):
    current = await state.get_state()
    if current not in {s.state for s in _recipient_picker_states()}:
        return
    await callback.answer()
    data = await state.get_data()
    cohort_type = data.get("recipient_cohort_type_pending")
    if not cohort_type:
        await safe_edit_text(callback, "Тип когорты утерян, начните заново.")
        return
    value = callback_data.value
    await state.update_data(
        recipient_config={"cohort_type": cohort_type, "cohort_value": value}
    )
    await _after_recipient_config(callback, state, f"{cohort_type}: {value}")


@router.callback_query(TriggerPickUserCB.filter())
async def cb_pick_user(
    callback: CallbackQuery, callback_data: TriggerPickUserCB, state: FSMContext
):
    current = await state.get_state()
    if current not in {s.state for s in _recipient_picker_states()}:
        return
    data = await state.get_data()
    selected: list[int] = list(data.get("users_selected") or [])
    tid = callback_data.telegram_id
    if tid in selected:
        selected.remove(tid)
    else:
        selected.append(tid)
    page = int(data.get("users_page") or 0)
    users, total_pages = await UserDAO.get_paginated(
        page=page, page_size=USERS_PAGE_SIZE, exclude_placeholders=True
    )
    await state.update_data(users_selected=selected)
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=trigger_users_keyboard(users, set(selected), page, total_pages)
    )


@router.callback_query(TriggerUsersDoneCB.filter())
async def cb_users_done(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current not in {s.state for s in _recipient_picker_states()}:
        return
    data = await state.get_data()
    selected: list[int] = list(data.get("users_selected") or [])
    if not selected:
        await callback.answer("Выберите хотя бы одного пользователя", show_alert=True)
        return
    await callback.answer()
    sorted_ids = sorted(selected)
    await state.update_data(recipient_config={"user_ids": sorted_ids})
    # Resolve names for summary
    names: list[str] = []
    for uid in sorted_ids:
        user = await UserDAO.find_one_or_none(telegram_id=uid)
        if user and user.name:
            names.append(user.name)
        elif user and user.username:
            names.append(f"@{user.username}")
        else:
            names.append("—")
    await _after_recipient_config(callback, state, ", ".join(names))


@router.callback_query(TriggerRecipientPageCB.filter())
async def cb_recipient_page(
    callback: CallbackQuery, callback_data: TriggerRecipientPageCB, state: FSMContext
):
    current = await state.get_state()
    if current not in {s.state for s in _recipient_picker_states()}:
        return
    await callback.answer()
    kind = callback_data.kind
    page = callback_data.page
    if kind == "role":
        roles = list(await RoleDAO.get_all())
        page_items, total_pages = get_page_slice(roles, page)
        await callback.message.edit_reply_markup(
            reply_markup=trigger_roles_keyboard(list(page_items), page, total_pages)
        )
    elif kind == "state":
        states = await CohortDAO.get_distinct_values("Status")
        page_items, total_pages = get_page_slice(states, page)
        await callback.message.edit_reply_markup(
            reply_markup=trigger_states_keyboard(list(page_items), page, total_pages)
        )
    elif kind == "ctype":
        types = await CohortDAO.get_distinct_types()
        page_items, total_pages = get_page_slice(types, page)
        await callback.message.edit_reply_markup(
            reply_markup=trigger_rcohort_types_keyboard(
                list(page_items), page, total_pages
            )
        )
    elif kind == "cval":
        data = await state.get_data()
        cohort_type = data.get("recipient_cohort_type_pending")
        if not cohort_type:
            return
        values = await CohortDAO.get_distinct_values(cohort_type)
        page_items, total_pages = get_page_slice(values, page)
        await callback.message.edit_reply_markup(
            reply_markup=trigger_rcohort_values_keyboard(
                list(page_items), page, total_pages
            )
        )
    elif kind == "user":
        data = await state.get_data()
        selected = set(data.get("users_selected") or [])
        users, total_pages = await UserDAO.get_paginated(
            page=page, page_size=USERS_PAGE_SIZE, exclude_placeholders=True
        )
        await state.update_data(users_page=page)
        await callback.message.edit_reply_markup(
            reply_markup=trigger_users_keyboard(users, selected, page, total_pages)
        )


@router.callback_query(TriggerRecipientBackCB.filter())
async def cb_recipient_back(
    callback: CallbackQuery, callback_data: TriggerRecipientBackCB, state: FSMContext
):
    current = await state.get_state()
    if current not in {s.state for s in _recipient_picker_states()}:
        return
    await callback.answer()
    step = callback_data.step
    data = await state.get_data()
    if step == "ctype":
        rt = data.get("recipient_type") or "by_cohort"
        await _show_recipient_picker(callback, rt, state)
        return
    # step == "type": back to recipient type selection
    if data.get("edit_rule_id"):
        await state.set_state(TriggerRuleEditFSM.editing_recipient_type)
        await safe_edit_text(
            callback,
            "Выберите новый тип получателей:",
            reply_markup=recipient_type_keyboard(),
        )
    else:
        await state.set_state(TriggerRuleBuilderFSM.choosing_recipient_type)
        await safe_edit_text(
            callback,
            "Выберите тип получателей:",
            reply_markup=recipient_type_keyboard(),
        )


@router.message(TriggerRuleBuilderFSM.setting_delay)
async def msg_delay(message: Message, state: FSMContext):
    try:
        delay = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return

    if delay < 0:
        await message.answer("Задержка не может быть отрицательной:")
        return

    await state.update_data(delay_seconds=delay)

    # Create rule
    data = await state.get_data()
    create_kwargs = dict(
        name=data["name"],
        trigger_type=data["trigger_type"],
        action_type=data["action_type"],
        recipient_type=data["recipient_type"],
        recipient_config=data.get("recipient_config"),
        action_config=data["action_config"],
        delay_seconds=delay,
        created_by=message.from_user.id,
    )
    if data.get("trigger_config"):
        create_kwargs["trigger_config"] = data["trigger_config"]
    if data.get("cron_expression"):
        create_kwargs["cron_expression"] = data["cron_expression"]
    if data.get("regularity"):
        create_kwargs["regularity"] = data["regularity"]
    if data.get("time_of_day"):
        h, m = data["time_of_day"].split(":")
        create_kwargs["time_of_day"] = time(int(h), int(m))
    rule = await TriggerRuleDAO.create(**create_kwargs)

    await state.clear()

    trigger_label = TRIGGER_TYPE_LABELS.get(
        rule.trigger_type.value, rule.trigger_type.value
    )
    action_label = ACTION_TYPE_LABELS.get(
        rule.action_type.value, rule.action_type.value
    )

    text, markup = await _build_rules_list_page(page=0)
    await message.answer(
        f"Правило <b>{e(rule.name)}</b> создано.\n\n"
        f"Триггер: {e(trigger_label)}\n"
        f"Действие: {e(action_label)}\n"
        f"Задержка: {delay} сек\n\n{text}",
        reply_markup=markup,
    )


# --- Edit rule FSM ---


async def _finish_edit(
    target: CallbackQuery | Message,
    state: FSMContext,
    **fields,
):
    data = await state.get_data()
    rule_id = data.get("edit_rule_id")
    rule = await TriggerRuleDAO.update(rule_id, **fields)
    await state.clear()
    if rule is None:
        text, markup = await _build_rules_list_page(page=0)
    else:
        text, markup = await _format_rule_detail(rule)
    if isinstance(target, CallbackQuery):
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(TriggerRuleEditMenuCB.filter())
async def cb_edit_menu(
    callback: CallbackQuery,
    callback_data: TriggerRuleEditMenuCB,
    state: FSMContext,
):
    rule = await TriggerRuleDAO.get_by_id(callback_data.rule_id)
    if not rule:
        await callback.answer(await UiTextService.get("trigger.rule_not_found"))
        return
    await state.clear()
    await state.update_data(edit_rule_id=rule.id)
    await state.set_state(TriggerRuleEditFSM.choosing_field)
    await callback.answer()
    await safe_edit_text(
        callback,
        f"Выберите параметр для редактирования — <b>{e(rule.name)}</b>:",
        reply_markup=rule_edit_menu_keyboard(rule),
    )


@router.callback_query(
    TriggerRuleEditFSM.choosing_field, TriggerRuleEditFieldCB.filter()
)
async def cb_edit_field(
    callback: CallbackQuery,
    callback_data: TriggerRuleEditFieldCB,
    state: FSMContext,
):
    data = await state.get_data()
    rule_id = data.get("edit_rule_id")
    rule = await TriggerRuleDAO.get_by_id(rule_id) if rule_id else None
    if not rule:
        await callback.answer(await UiTextService.get("trigger.rule_not_found"))
        return
    await callback.answer()
    field = callback_data.field

    if field == "nm":
        await state.set_state(TriggerRuleEditFSM.editing_name)
        await safe_edit_text(
            callback,
            "Введите новое название правила:",
            reply_markup=cancel_keyboard(),
        )
    elif field == "tt":
        await state.set_state(TriggerRuleEditFSM.editing_trigger_type)
        await safe_edit_text(
            callback,
            "Выберите новый тип триггера:",
            reply_markup=trigger_type_keyboard(),
        )
    elif field == "rt":
        await state.set_state(TriggerRuleEditFSM.editing_recipient_type)
        await safe_edit_text(
            callback,
            "Выберите новый тип получателей:",
            reply_markup=recipient_type_keyboard(),
        )
    elif field == "cr":
        await state.set_state(TriggerRuleEditFSM.editing_cron)
        await safe_edit_text(
            callback,
            "Введите новое cron-выражение (5 полей):\n"
            "<code>минуты часы день_месяца месяц день_недели</code>",
            reply_markup=cancel_keyboard(),
        )
    elif field == "rg":
        await state.set_state(TriggerRuleEditFSM.editing_regularity)
        await safe_edit_text(
            callback,
            "Выберите новую регулярность:",
            reply_markup=regularity_keyboard(),
        )
    elif field == "td":
        await state.set_state(TriggerRuleEditFSM.editing_time_of_day)
        await safe_edit_text(
            callback,
            "Введите новое время отправки (HH:MM, UTC):",
            reply_markup=cancel_keyboard(),
        )
    elif field == "dl":
        await state.set_state(TriggerRuleEditFSM.editing_delay)
        await safe_edit_text(
            callback,
            "Введите новую задержку в секундах (0 = немедленно):",
            reply_markup=cancel_keyboard(),
        )
    elif field == "dm":
        await state.set_state(TriggerRuleEditFSM.editing_delay_mode)
        await safe_edit_text(
            callback,
            "Выберите новый режим задержки:",
            reply_markup=delay_mode_keyboard(),
        )
    elif field == "ac":
        service = SurveyTemplateService()
        templates = await service.list_active()
        if not templates:
            await safe_edit_text(
                callback,
                "Нет активных шаблонов. Сначала создайте опрос или рассылку.",
            )
            await state.clear()
            return
        await state.set_state(TriggerRuleEditFSM.editing_survey_template)
        await safe_edit_text(
            callback,
            "Выберите новый шаблон (опрос или рассылку):",
            reply_markup=survey_templates_keyboard(templates),
        )
    elif field == "rc":
        rt = rule.recipient_type.value
        await state.set_state(TriggerRuleEditFSM.editing_recipient_config)
        await _show_recipient_picker(callback, rt, state)
    elif field == "tc":
        types = await CohortDAO.get_distinct_types()
        await state.set_state(TriggerRuleEditFSM.editing_cohort_type)
        await safe_edit_text(
            callback,
            "Выберите тип когорты для отслеживания:",
            reply_markup=cohort_type_keyboard(types),
        )


@router.message(TriggerRuleEditFSM.editing_name)
async def msg_edit_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым:")
        return
    await _finish_edit(message, state, name=name)


@router.callback_query(TriggerRuleEditFSM.editing_trigger_type, TriggerTypeCB.filter())
async def cb_edit_trigger_type(
    callback: CallbackQuery, callback_data: TriggerTypeCB, state: FSMContext
):
    await callback.answer()
    await _finish_edit(callback, state, trigger_type=TriggerType(callback_data.value))


@router.callback_query(
    TriggerRuleEditFSM.editing_recipient_type, TriggerRecipientTypeCB.filter()
)
async def cb_edit_recipient_type(
    callback: CallbackQuery,
    callback_data: TriggerRecipientTypeCB,
    state: FSMContext,
):
    await callback.answer()
    rt = callback_data.value
    data = await state.get_data()
    rule_id = data.get("edit_rule_id")
    # Persist the new recipient type first, then let user pick config
    await TriggerRuleDAO.update(
        rule_id, recipient_type=RecipientType(rt), recipient_config=None
    )
    if rt in ("by_role", "by_state", "by_cohort", "specific_users"):
        await state.set_state(TriggerRuleEditFSM.editing_recipient_config)
        await _show_recipient_picker(callback, rt, state)
    else:
        await _finish_edit(callback, state)


@router.message(TriggerRuleEditFSM.editing_cron)
async def msg_edit_cron(message: Message, state: FSMContext):
    expr = (message.text or "").strip()
    err = _validate_cron(expr)
    if err:
        await message.answer(f"{err} Попробуйте снова:")
        return
    await _finish_edit(message, state, cron_expression=expr)


@router.callback_query(
    TriggerRuleEditFSM.editing_regularity, TriggerRegularityCB.filter()
)
async def cb_edit_regularity(
    callback: CallbackQuery, callback_data: TriggerRegularityCB, state: FSMContext
):
    await callback.answer()
    await _finish_edit(callback, state, regularity=Regularity(callback_data.value))


@router.message(TriggerRuleEditFSM.editing_time_of_day)
async def msg_edit_time_of_day(message: Message, state: FSMContext):
    t, err = _parse_time_of_day(message.text or "")
    if err:
        await message.answer(err)
        return
    await _finish_edit(message, state, time_of_day=t)


@router.message(TriggerRuleEditFSM.editing_delay)
async def msg_edit_delay(message: Message, state: FSMContext):
    try:
        delay = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    if delay < 0:
        await message.answer("Задержка не может быть отрицательной:")
        return
    await _finish_edit(message, state, delay_seconds=delay)


@router.callback_query(
    TriggerRuleEditFSM.editing_delay_mode, TriggerDelayModeCB.filter()
)
async def cb_edit_delay_mode(
    callback: CallbackQuery, callback_data: TriggerDelayModeCB, state: FSMContext
):
    await callback.answer()
    await _finish_edit(callback, state, delay_mode=DelayMode(callback_data.value))


@router.callback_query(
    TriggerRuleEditFSM.editing_survey_template, TriggerSurveyTemplateCB.filter()
)
async def cb_edit_survey_template(
    callback: CallbackQuery,
    callback_data: TriggerSurveyTemplateCB,
    state: FSMContext,
):
    from src.models.survey_template import TemplateKind

    service = SurveyTemplateService()
    template = await service.get(callback_data.template_id)
    await callback.answer()
    action_config = {
        "survey_template_id": template.id,
        "survey_title": template.title,
    }
    if template.kind == TemplateKind.broadcast:
        action_config["escalatable"] = False
    await _finish_edit(callback, state, action_config=action_config)


@router.callback_query(
    TriggerRuleEditFSM.editing_cohort_type, TriggerCohortTypeCB.filter()
)
async def cb_edit_cohort_type(
    callback: CallbackQuery,
    callback_data: TriggerCohortTypeCB,
    state: FSMContext,
):
    cohort_type = callback_data.value
    await state.update_data(edit_cohort_type=cohort_type)
    await callback.answer()
    if cohort_type == "*":
        await state.set_state(TriggerRuleEditFSM.editing_cohort_from)
        await safe_edit_text(
            callback,
            "Начальное значение (from):",
            reply_markup=cohort_wildcard_keyboard(),
        )
    else:
        values = await CohortDAO.get_distinct_values(cohort_type)
        await state.set_state(TriggerRuleEditFSM.editing_cohort_from)
        await safe_edit_text(
            callback,
            "Выберите начальное значение (from):",
            reply_markup=cohort_value_keyboard(values),
        )


@router.callback_query(
    TriggerRuleEditFSM.editing_cohort_from, TriggerCohortValueCB.filter()
)
async def cb_edit_cohort_from(
    callback: CallbackQuery,
    callback_data: TriggerCohortValueCB,
    state: FSMContext,
):
    await state.update_data(edit_cohort_from=callback_data.value)
    await callback.answer()
    data = await state.get_data()
    cohort_type = data.get("edit_cohort_type", "*")
    if cohort_type == "*":
        await state.set_state(TriggerRuleEditFSM.editing_cohort_to)
        await safe_edit_text(
            callback,
            "Конечное значение (to):",
            reply_markup=cohort_wildcard_keyboard(),
        )
    else:
        values = await CohortDAO.get_distinct_values(cohort_type)
        await state.set_state(TriggerRuleEditFSM.editing_cohort_to)
        await safe_edit_text(
            callback,
            "Выберите конечное значение (to):",
            reply_markup=cohort_value_keyboard(values),
        )


@router.callback_query(
    TriggerRuleEditFSM.editing_cohort_to, TriggerCohortValueCB.filter()
)
async def cb_edit_cohort_to(
    callback: CallbackQuery,
    callback_data: TriggerCohortValueCB,
    state: FSMContext,
):
    data = await state.get_data()
    trigger_config = {
        "cohort_type": data.get("edit_cohort_type", "*"),
        "from_value": data.get("edit_cohort_from", "*"),
        "to_value": callback_data.value,
    }
    await callback.answer()
    await _finish_edit(callback, state, trigger_config=trigger_config)


# --- Cancel ---


@router.callback_query(TriggerActionCB.filter(F.action == "cancel"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    text, markup = await _build_rules_list_page(page=0)
    await safe_edit_text(callback, text, reply_markup=markup)
