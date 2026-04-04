import logging
from datetime import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

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
from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.trigger_rules import (
    ACTION_TYPE_LABELS,
    RECIPIENT_TYPE_LABELS,
    TRIGGER_TYPE_LABELS,
    action_type_keyboard,
    cancel_keyboard,
    cohort_type_keyboard,
    cohort_value_keyboard,
    cohort_wildcard_keyboard,
    confirm_delete_rule_keyboard,
    manual_send_rules_keyboard,
    recipient_type_keyboard,
    regularity_keyboard,
    rule_detail_keyboard,
    rules_list_keyboard,
    schedule_mode_keyboard,
    survey_templates_keyboard,
    trigger_menu_keyboard,
    trigger_type_keyboard,
)
from src.bot.states.trigger_rules import TriggerRuleBuilderFSM
from src.bot.utils import safe_edit_text
from src.dao.trigger_rule import TriggerRuleDAO
from src.services.events.dispatcher import EventDispatcher
from src.services.survey_template import SurveyTemplateService
from src.services.ui_text import UiTextService
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="trigger_rules")
router.message.filter(PermissionFilter("manage_triggers"))
router.callback_query.filter(PermissionFilter("manage_triggers"))


# --- Menu ---


@router.callback_query(F.data == "menu_triggers")
async def cb_triggers_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await safe_edit_text(
        callback,
        await UiTextService.get("trigger.menu.title"),
        reply_markup=trigger_menu_keyboard(),
    )


# --- List ---


@router.callback_query(TriggerActionCB.filter(F.action == "list"))
async def cb_list_rules(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    rules = await TriggerRuleDAO.get_all()
    if not rules:
        await callback.answer(await UiTextService.get("trigger.no_rules"))
        return
    await callback.answer()
    await safe_edit_text(
        callback,
        await UiTextService.get("trigger.list.header"),
        reply_markup=rules_list_keyboard(rules),
    )


@router.callback_query(TriggerRuleDetailCB.filter())
async def cb_rule_detail(callback: CallbackQuery, callback_data: TriggerRuleDetailCB):
    rule = await TriggerRuleDAO.get_by_id(callback_data.rule_id)
    if not rule:
        await callback.answer(await UiTextService.get("trigger.rule_not_found"))
        return

    trigger_label = TRIGGER_TYPE_LABELS.get(
        rule.trigger_type.value, rule.trigger_type.value
    )
    action_label = ACTION_TYPE_LABELS.get(
        rule.action_type.value, rule.action_type.value
    )
    recipient_label = RECIPIENT_TYPE_LABELS.get(
        rule.recipient_type.value, rule.recipient_type.value
    )
    status = "Активно" if rule.is_active else "Отключено"

    text = (
        f"<b>{e(rule.name)}</b>\n\n"
        f"Триггер: {e(trigger_label)}\n"
        f"Действие: {e(action_label)}\n"
        f"Получатели: {e(recipient_label)}\n"
        f"Задержка: {rule.delay_seconds} сек ({e(rule.delay_mode.value)})\n"
        f"Статус: {status}"
    )

    if rule.cron_expression:
        text += f"\nCron: <code>{e(rule.cron_expression)}</code>"

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

    await callback.answer()
    await safe_edit_text(callback, text, reply_markup=rule_detail_keyboard(rule))


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
        await safe_edit_text(
            callback,
            await UiTextService.get("trigger.rule_not_found"),
            reply_markup=trigger_menu_keyboard(),
        )
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
        await safe_edit_text(
            callback,
            await UiTextService.get("trigger.list.header"),
            reply_markup=rules_list_keyboard(rules),
        )
    else:
        await safe_edit_text(
            callback,
            await UiTextService.get("trigger.menu.title"),
            reply_markup=trigger_menu_keyboard(),
        )


# --- Manual send ---


@router.callback_query(TriggerActionCB.filter(F.action == "manual_send"))
async def cb_manual_send_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    rules = await TriggerRuleDAO.get_all_active()
    if not rules:
        await callback.answer(await UiTextService.get("trigger.no_rules"))
        return
    await callback.answer()
    await safe_edit_text(
        callback,
        "Выберите правило для ручной отправки:",
        reply_markup=manual_send_rules_keyboard(rules),
    )


@router.callback_query(TriggerRuleSendCB.filter())
async def cb_send_now(callback: CallbackQuery, callback_data: TriggerRuleSendCB):
    rule = await TriggerRuleDAO.get_by_id(callback_data.rule_id)
    if not rule:
        await callback.answer(await UiTextService.get("trigger.rule_not_found"))
        return

    await callback.answer("Отправляю...")

    count = await EventDispatcher.execute_rule_manually(
        rule_id=rule.id,
        context={"admin_id": callback.from_user.id},
        bot=callback.bot,
    )

    await safe_edit_text(
        callback,
        f"Правило <b>{e(rule.name)}</b> выполнено.\nОтправлено: {count} получателям.",
        reply_markup=trigger_menu_keyboard(),
    )


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
        await state.set_state(TriggerRuleBuilderFSM.choosing_action_type)
        await safe_edit_text(
            callback, "Выберите действие:", reply_markup=action_type_keyboard()
        )


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
        from src.dao.cohort import CohortDAO

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
        from src.dao.cohort import CohortDAO

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

    await state.set_state(TriggerRuleBuilderFSM.choosing_action_type)
    await safe_edit_text(
        callback, "Выберите действие:", reply_markup=action_type_keyboard()
    )


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


@router.message(TriggerRuleBuilderFSM.entering_cron_expression)
async def msg_cron_expression(message: Message, state: FSMContext):
    expr = message.text.strip()
    error = _validate_cron(expr)
    if error:
        await message.answer(f"{error} Попробуйте снова:")
        return
    await state.update_data(cron_expression=expr)
    await state.set_state(TriggerRuleBuilderFSM.choosing_action_type)
    await message.answer("Выберите действие:", reply_markup=action_type_keyboard())


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


@router.message(TriggerRuleBuilderFSM.entering_time_of_day)
async def msg_time_of_day(message: Message, state: FSMContext):
    text = message.text.strip()
    parts = text.split(":")
    if len(parts) != 2:
        await message.answer("Формат: HH:MM (например, 09:30). Попробуйте снова:")
        return
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        await message.answer("Формат: HH:MM (например, 09:30). Попробуйте снова:")
        return
    if not (0 <= h <= 23 and 0 <= m <= 59):
        await message.answer("Часы: 0-23, минуты: 0-59. Попробуйте снова:")
        return
    await state.update_data(time_of_day=f"{h:02d}:{m:02d}")
    await state.set_state(TriggerRuleBuilderFSM.choosing_action_type)
    await message.answer("Выберите действие:", reply_markup=action_type_keyboard())


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_action_type, TriggerActionTypeCB.filter()
)
async def cb_action_type(
    callback: CallbackQuery, callback_data: TriggerActionTypeCB, state: FSMContext
):
    await state.update_data(action_type=callback_data.value)
    await callback.answer()

    if callback_data.value == "send_notification":
        await state.set_state(TriggerRuleBuilderFSM.configuring_action_text)
        await safe_edit_text(
            callback,
            "Введите текст уведомления (поддерживается HTML):",
            reply_markup=cancel_keyboard(),
        )
    elif callback_data.value == "send_survey":
        service = SurveyTemplateService()
        templates = await service.list_active()
        if not templates:
            await safe_edit_text(
                callback, "Нет активных шаблонов опросов. Сначала создайте опрос."
            )
            await state.clear()
            return
        await state.set_state(TriggerRuleBuilderFSM.choosing_survey_template)
        await safe_edit_text(
            callback,
            "Выберите шаблон опроса:",
            reply_markup=survey_templates_keyboard(templates),
        )


@router.message(TriggerRuleBuilderFSM.configuring_action_text)
async def msg_action_text(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text:
        await message.answer("Текст не может быть пустым:")
        return
    await state.update_data(action_config={"text": text})
    await state.set_state(TriggerRuleBuilderFSM.choosing_recipient_type)
    await message.answer(
        "Выберите тип получателей:", reply_markup=recipient_type_keyboard()
    )


@router.callback_query(
    TriggerRuleBuilderFSM.choosing_survey_template, TriggerSurveyTemplateCB.filter()
)
async def cb_choose_template(
    callback: CallbackQuery, callback_data: TriggerSurveyTemplateCB, state: FSMContext
):
    service = SurveyTemplateService()
    template = await service.get(callback_data.template_id)
    await state.update_data(
        action_config={
            "survey_template_id": template.id,
            "survey_title": template.title,
        }
    )
    await state.set_state(TriggerRuleBuilderFSM.choosing_recipient_type)
    await callback.answer()
    await safe_edit_text(
        callback, "Выберите тип получателей:", reply_markup=recipient_type_keyboard()
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

    # For types that need config, ask for it
    if rt in ("by_role", "by_state", "by_cohort", "specific_users"):
        await state.set_state(TriggerRuleBuilderFSM.configuring_recipients)
        hints = {
            "by_role": "Введите название роли (например: mentor):",
            "by_state": "Введите статус (greeting/hold/study/search/offer):",
            "by_cohort": "Введите значение когорты:",
            "specific_users": "Введите Telegram ID пользователей через запятую:",
        }
        await safe_edit_text(callback, hints[rt], reply_markup=cancel_keyboard())
    else:
        await state.set_state(TriggerRuleBuilderFSM.setting_delay)
        await safe_edit_text(
            callback,
            "Задержка отправки в секундах (0 = немедленно):",
            reply_markup=cancel_keyboard(),
        )


@router.message(TriggerRuleBuilderFSM.configuring_recipients)
async def msg_recipient_config(message: Message, state: FSMContext):
    data = await state.get_data()
    rt = data["recipient_type"]
    text = message.text.strip()

    config = {}
    if rt == "by_role":
        config = {"role_name": text}
    elif rt == "by_state":
        config = {"state": text}
    elif rt == "by_cohort":
        config = {"cohort_value": text}
    elif rt == "specific_users":
        user_ids = [
            int(uid.strip()) for uid in text.split(",") if uid.strip().isdigit()
        ]
        if not user_ids:
            await message.answer(
                "Введите хотя бы один числовой Telegram ID через запятую."
            )
            return
        config = {"user_ids": user_ids}

    await state.update_data(recipient_config=config)
    await state.set_state(TriggerRuleBuilderFSM.setting_delay)
    await message.answer(
        "Задержка отправки в секундах (0 = немедленно):", reply_markup=cancel_keyboard()
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

    await message.answer(
        f"Правило <b>{e(rule.name)}</b> создано.\n\n"
        f"Триггер: {e(trigger_label)}\n"
        f"Действие: {e(action_label)}\n"
        f"Задержка: {delay} сек",
        reply_markup=trigger_menu_keyboard(),
    )


# --- Cancel ---


@router.callback_query(TriggerActionCB.filter(F.action == "cancel"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    await safe_edit_text(
        callback,
        await UiTextService.get("trigger.menu.title"),
        reply_markup=trigger_menu_keyboard(),
    )
