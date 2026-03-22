import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

from src.bot.filters.permission import PermissionFilter
from src.bot.keyboards.mailings import (
    mailings_menu_keyboard,
    mailing_type_keyboard,
    select_users_keyboard,
    select_states_keyboard,
    select_cohort_type_keyboard,
    select_cohorts_keyboard,
    regularity_keyboard,
    delete_mailings_keyboard,
)
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.callbacks.rule import (
    MailingTypeCB,
    ToggleUserCB,
    ToggleStateCB,
    ToggleCohortCB,
    ChooseRegularityCB,
    MailingFinishUsersCB,
    MailingFinishStatesCB,
    MailingFinishCohortsCB,
    ToggleDeleteUserRuleCB,
    ToggleDeleteStateRuleCB,
    ToggleDeleteCohortRuleCB,
    DeleteMailingsFinishCB,
)
from src.bot.states.mailings import MailingFSM
from src.core.config import settings
from src.dao.user import UserDAO
from src.dao.rule import RuleDAO
from src.dao.notion_cache import NotionCacheDAO
from src.models.user import State
from src.models.enums import Regularity
from src.utils.escape import e

logger = logging.getLogger(__name__)

router = Router(name="mailings")
router.message.filter(PermissionFilter("manage_mailings"))
router.callback_query.filter(PermissionFilter("manage_mailings"))


REGULARITY_TO_OFFSET = {
    Regularity.day: 1,
    Regularity.week: 7,
    Regularity.fortnight: 14,
    Regularity.month: 30,
}


@router.callback_query(F.data == "menu_mailings")
async def cb_menu_mailings(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("Меню Рассылок", reply_markup=mailings_menu_keyboard())


@router.callback_query(F.data == "mailings_menu")
async def cb_mailings_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("Меню Рассылок", reply_markup=mailings_menu_keyboard())


@router.callback_query(F.data == "mailings_list")
async def cb_mailings_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()

    user_rules = await RuleDAO.list_user_rules()
    state_rules = await RuleDAO.list_state_rules()
    cohort_rules = await RuleDAO.list_cohort_rules()

    parts = ["<b>Список рассылок:</b>", ""]
    if user_rules:
        parts.append("<b>Индивидуальные:</b>")
        for rule in user_rules:
            parts.append(
                f"• Название: {e(rule.name) or '—'}\n"
                f"  Пользователь: @{e(rule.user.username)} ({e(rule.user.name)})\n"
                f"  Регулярность: {e(rule.regularity.value)}\n"
                f"  Текст: {e(rule.text) or '—'}"
            )
    if state_rules:
        parts.append("")
        parts.append("<b>По статусам:</b>")
        for rule in state_rules:
            parts.append(
                f"• Название: {e(rule.name) or '—'}\n"
                f"  Статус: {e(rule.user_state.value)}\n"
                f"  Регулярность: {e(rule.regularity.value)}\n"
                f"  Текст: {e(rule.text) or '—'}"
            )
    if cohort_rules:
        parts.append("")
        parts.append("<b>По когортам:</b>")
        for rule in cohort_rules:
            parts.append(
                f"• Название: {e(rule.name) or '—'}\n"
                f"  Когорта: {e(rule.cohort_type)}: {e(rule.cohort_value)}\n"
                f"  Регулярность: {e(rule.regularity.value)}\n"
                f"  Текст: {e(rule.text) or '—'}"
            )

    if not user_rules and not state_rules and not cohort_rules:
        parts = ["<b>Список рассылок пуст.</b>"]

    await callback.message.edit_text("\n".join(parts), reply_markup=mailings_menu_keyboard())


@router.callback_query(F.data == "mailings_add")
async def cb_mailings_add(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(MailingFSM.choosing_type)
    await callback.answer()
    await callback.message.edit_text("Выберите тип рассылки:", reply_markup=mailing_type_keyboard())


@router.callback_query(MailingTypeCB.filter())
async def cb_choose_type(callback: CallbackQuery, callback_data: MailingTypeCB, state: FSMContext):
    kind = callback_data.kind
    await state.update_data(kind=kind)
    await state.set_state(MailingFSM.waiting_title)
    await callback.answer()
    await callback.message.edit_text("Введите название рассылки:")


@router.callback_query(F.data == "mailings_delete")
async def cb_mailings_delete(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(MailingFSM.deleting_rules)
    await state.update_data(del_user_rules=[], del_state_rules=[], del_cohort_rules=[])

    user_rules = await RuleDAO.list_user_rules()
    state_rules = await RuleDAO.list_state_rules()
    cohort_rules = await RuleDAO.list_cohort_rules()

    await callback.answer()
    await callback.message.edit_text(
        "Выберите рассылки для удаления:",
        reply_markup=delete_mailings_keyboard(user_rules, state_rules, cohort_rules, set(), set(), set()),
    )


@router.callback_query(
    StateFilter(MailingFSM.deleting_rules),
    ToggleDeleteUserRuleCB.filter(),
)
async def cb_toggle_delete_user_rule(
    callback: CallbackQuery,
    callback_data: ToggleDeleteUserRuleCB,
    state: FSMContext,
):
    data = await state.get_data()
    sel_users = set(data.get("del_user_rules", []))
    if callback_data.rule_id in sel_users:
        sel_users.remove(callback_data.rule_id)
    else:
        sel_users.add(callback_data.rule_id)
    await state.update_data(del_user_rules=list(sel_users))

    user_rules = await RuleDAO.list_user_rules()
    state_rules = await RuleDAO.list_state_rules()
    cohort_rules = await RuleDAO.list_cohort_rules()

    await callback.answer()
    await callback.message.edit_text(
        "Выберите рассылки для удаления:",
        reply_markup=delete_mailings_keyboard(
            user_rules, state_rules, cohort_rules,
            sel_users,
            set(data.get("del_state_rules", [])),
            set(data.get("del_cohort_rules", [])),
        ),
    )


@router.callback_query(
    StateFilter(MailingFSM.deleting_rules),
    ToggleDeleteStateRuleCB.filter(),
)
async def cb_toggle_delete_state_rule(
    callback: CallbackQuery,
    callback_data: ToggleDeleteStateRuleCB,
    state: FSMContext,
):
    data = await state.get_data()
    sel_states = set(data.get("del_state_rules", []))
    if callback_data.rule_id in sel_states:
        sel_states.remove(callback_data.rule_id)
    else:
        sel_states.add(callback_data.rule_id)
    await state.update_data(del_state_rules=list(sel_states))

    user_rules = await RuleDAO.list_user_rules()
    state_rules = await RuleDAO.list_state_rules()
    cohort_rules = await RuleDAO.list_cohort_rules()

    await callback.answer()
    await callback.message.edit_text(
        "Выберите рассылки для удаления:",
        reply_markup=delete_mailings_keyboard(
            user_rules, state_rules, cohort_rules,
            set(data.get("del_user_rules", [])),
            sel_states,
            set(data.get("del_cohort_rules", [])),
        ),
    )


@router.callback_query(
    StateFilter(MailingFSM.deleting_rules),
    ToggleDeleteCohortRuleCB.filter(),
)
async def cb_toggle_delete_cohort_rule(
    callback: CallbackQuery,
    callback_data: ToggleDeleteCohortRuleCB,
    state: FSMContext,
):
    data = await state.get_data()
    sel_cohorts = set(data.get("del_cohort_rules", []))
    if callback_data.rule_id in sel_cohorts:
        sel_cohorts.remove(callback_data.rule_id)
    else:
        sel_cohorts.add(callback_data.rule_id)
    await state.update_data(del_cohort_rules=list(sel_cohorts))

    user_rules = await RuleDAO.list_user_rules()
    state_rules = await RuleDAO.list_state_rules()
    cohort_rules = await RuleDAO.list_cohort_rules()

    await callback.answer()
    await callback.message.edit_text(
        "Выберите рассылки для удаления:",
        reply_markup=delete_mailings_keyboard(
            user_rules, state_rules, cohort_rules,
            set(data.get("del_user_rules", [])),
            set(data.get("del_state_rules", [])),
            sel_cohorts,
        ),
    )


@router.callback_query(
    StateFilter(MailingFSM.deleting_rules),
    DeleteMailingsFinishCB.filter(),
)
async def cb_delete_mailings_finish(
    callback: CallbackQuery,
    callback_data: DeleteMailingsFinishCB,
    state: FSMContext,
):
    data = await state.get_data()
    sel_users = set(data.get("del_user_rules", []))
    sel_states = set(data.get("del_state_rules", []))
    sel_cohorts = set(data.get("del_cohort_rules", []))

    if not sel_users and not sel_states and not sel_cohorts:
        await callback.answer("Нужно выбрать хотя бы одну рассылку.", show_alert=True)
        return

    if sel_users:
        await RuleDAO.delete_user_rules(sel_users)
    if sel_states:
        await RuleDAO.delete_state_rules(sel_states)
    if sel_cohorts:
        await RuleDAO.delete_cohort_rules(sel_cohorts)

    logger.info(
        "Mailings deleted: user_rules=%d state_rules=%d cohort_rules=%d",
        len(sel_users), len(sel_states), len(sel_cohorts),
    )
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "Выбранные рассылки удалены.",
        reply_markup=mailings_menu_keyboard(),
    )


@router.message(StateFilter(MailingFSM.waiting_title))
async def msg_mailing_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым. Введите название.")
        return

    data = await state.get_data()
    kind = data.get("kind")

    await state.update_data(title=title)

    if kind == "individual":
        users = await UserDAO.get_all()
        await state.update_data(selected_users=[])
        await state.set_state(MailingFSM.choosing_users)
        await message.answer(
            "Выберите пользователей (можно несколько), затем нажмите «Готово».",
            reply_markup=select_users_keyboard(users, set()),
        )
    elif kind == "state":
        await state.update_data(selected_states=[])
        await state.set_state(MailingFSM.choosing_states)
        await message.answer(
            "Выберите статусы (можно несколько), затем нажмите «Готово».",
            reply_markup=select_states_keyboard(set()),
        )
    else:
        # Cohort: first choose cohort type, then values
        if settings.NOTION_TOKEN and settings.NOTION_DATABASE_ID:
            from src.services.notion_client import NotionService
            notion = NotionService(settings.NOTION_TOKEN, settings.NOTION_DATABASE_ID)
            try:
                types = await notion.get_cohort_types()
            finally:
                await notion.close()
        else:
            types = []

        if not types:
            await message.answer(
                "Типы когорт не найдены. Настройте Notion.",
                reply_markup=mailings_menu_keyboard(),
            )
            await state.clear()
            return

        await state.update_data(selected_cohorts=[])
        await state.set_state(MailingFSM.choosing_cohort_type)
        await message.answer(
            "Выберите тип когорты для рассылки:",
            reply_markup=select_cohort_type_keyboard(types),
        )


# === Cohort type selection for mailings ===

@router.callback_query(
    StateFilter(MailingFSM.choosing_cohort_type),
    F.data.startswith("mail_ctype:"),
)
async def cb_choose_cohort_type(callback: CallbackQuery, state: FSMContext):
    cohort_type = callback.data.split(":", 1)[1]
    await state.update_data(cohort_type=cohort_type, selected_cohorts=[])

    # Get available values from cache
    values = await NotionCacheDAO.get_distinct_values(cohort_type)
    if not values:
        # Fallback: get from Notion schema
        if settings.NOTION_TOKEN and settings.NOTION_DATABASE_ID:
            from src.services.notion_client import NotionService
            notion = NotionService(settings.NOTION_TOKEN, settings.NOTION_DATABASE_ID)
            try:
                values = await notion.get_options(cohort_type)
            finally:
                await notion.close()

    if not values:
        await callback.answer()
        await callback.message.edit_text(
            f'Нет опций для типа "{cohort_type}".',
            reply_markup=mailings_menu_keyboard(),
        )
        await state.clear()
        return

    await state.set_state(MailingFSM.choosing_cohorts)
    await callback.answer()
    await callback.message.edit_text(
        f"Выберите значения <b>{e(cohort_type)}</b> (можно несколько), затем нажмите «Готово».",
        reply_markup=select_cohorts_keyboard(cohort_type, values, set()),
    )


@router.callback_query(StateFilter(MailingFSM.choosing_users), ToggleUserCB.filter())
async def cb_toggle_user(callback: CallbackQuery, callback_data: ToggleUserCB, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("selected_users", []))
    if callback_data.user_id in selected:
        selected.remove(callback_data.user_id)
    else:
        selected.add(callback_data.user_id)
    await state.update_data(selected_users=list(selected))

    users = await UserDAO.get_all()
    await callback.answer()
    await callback.message.edit_text(
        "Выберите пользователей (можно несколько), затем нажмите «Готово».",
        reply_markup=select_users_keyboard(users, selected),
    )


@router.callback_query(StateFilter(MailingFSM.choosing_users), MailingFinishUsersCB.filter())
async def cb_finish_users(callback: CallbackQuery, callback_data: MailingFinishUsersCB, state: FSMContext):
    data = await state.get_data()
    selected: set[int] = set(data.get("selected_users", set()))
    if not selected:
        await callback.answer("Нужно выбрать хотя бы одного пользователя.", show_alert=True)
        return

    await state.set_state(MailingFSM.waiting_text)
    await callback.answer()
    await callback.message.edit_text("Введите текст рассылки:")


@router.callback_query(StateFilter(MailingFSM.choosing_states), ToggleStateCB.filter())
async def cb_toggle_state(callback: CallbackQuery, callback_data: ToggleStateCB, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("selected_states", []))
    state_name = callback_data.state.value
    if state_name in selected:
        selected.remove(state_name)
    else:
        selected.add(state_name)
    await state.update_data(selected_states=list(selected))

    await callback.answer()
    try:
        await callback.message.edit_text(
            "Выберите статусы (можно несколько), затем нажмите «Готово».",
            reply_markup=select_states_keyboard(selected),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(StateFilter(MailingFSM.choosing_states), MailingFinishStatesCB.filter())
async def cb_finish_states(callback: CallbackQuery, callback_data: MailingFinishStatesCB, state: FSMContext):
    data = await state.get_data()
    selected_names = set(data.get("selected_states", []))
    if not selected_names:
        await callback.answer("Нужно выбрать хотя бы один статус.", show_alert=True)
        return

    await state.set_state(MailingFSM.waiting_text)
    await callback.answer()
    await callback.message.edit_text("Введите текст рассылки:")


@router.callback_query(StateFilter(MailingFSM.choosing_cohorts), ToggleCohortCB.filter())
async def cb_toggle_cohort(callback: CallbackQuery, callback_data: ToggleCohortCB, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("selected_cohorts", []))
    cohort_value = callback_data.cohort_value
    if cohort_value in selected:
        selected.remove(cohort_value)
    else:
        selected.add(cohort_value)
    await state.update_data(selected_cohorts=list(selected))

    cohort_type = data.get("cohort_type", callback_data.cohort_type)

    # Get values from cache or Notion
    values = await NotionCacheDAO.get_distinct_values(cohort_type)
    if not values and settings.NOTION_TOKEN and settings.NOTION_DATABASE_ID:
        from src.services.notion_client import NotionService
        notion = NotionService(settings.NOTION_TOKEN, settings.NOTION_DATABASE_ID)
        try:
            values = await notion.get_options(cohort_type)
        finally:
            await notion.close()

    await callback.answer()
    await callback.message.edit_text(
        f"Выберите значения <b>{e(cohort_type)}</b> (можно несколько), затем нажмите «Готово».",
        reply_markup=select_cohorts_keyboard(cohort_type, values, selected),
    )


@router.callback_query(StateFilter(MailingFSM.choosing_cohorts), MailingFinishCohortsCB.filter())
async def cb_finish_cohorts(callback: CallbackQuery, callback_data: MailingFinishCohortsCB, state: FSMContext):
    data = await state.get_data()
    selected: set[str] = set(data.get("selected_cohorts", set()))
    if not selected:
        await callback.answer("Нужно выбрать хотя бы одну когорту.", show_alert=True)
        return

    await state.set_state(MailingFSM.waiting_text)
    await callback.answer()
    await callback.message.edit_text("Введите текст рассылки:")


@router.message(StateFilter(MailingFSM.waiting_text))
async def msg_mailing_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст не может быть пустым. Введите текст рассылки.")
        return

    await state.update_data(text=text)
    await state.set_state(MailingFSM.choosing_regularity)

    await message.answer(
        "Выберите регулярность:",
        reply_markup=regularity_keyboard(),
    )


@router.callback_query(StateFilter(MailingFSM.choosing_regularity), ChooseRegularityCB.filter())
async def cb_choose_regularity(
    callback: CallbackQuery,
    callback_data: ChooseRegularityCB,
    state: FSMContext,
):
    data = await state.get_data()
    kind = data.get("kind")
    title = data.get("title")
    text_body = data.get("text")

    regularity = callback_data.regularity
    author_id = callback.from_user.id

    await callback.answer()

    if kind == "individual":
        selected: set[int] = set(data.get("selected_users", set()))
        await RuleDAO.create_user_rules(
            user_ids=selected,
            name=title,
            text=text_body,
            regularity=regularity,
            author_id=author_id,
        )
        logger.info(
            "Mailing created: kind=individual name=%s users=%d author=%s",
            title, len(selected), author_id,
        )
        await state.clear()
        await callback.message.edit_text(
            "Индивидуальная рассылка создана.",
            reply_markup=mailings_menu_keyboard(),
        )
    elif kind == "state":
        selected_state_names = set(data.get("selected_states", []))
        selected_states = {State(name) for name in selected_state_names}
        offset_days = REGULARITY_TO_OFFSET.get(regularity, None)
        await RuleDAO.create_state_rules(
            states=selected_states,
            name=title,
            text=text_body,
            regularity=regularity,
            author_id=author_id,
            offset_days=offset_days,
        )
        logger.info(
            "Mailing created: kind=state name=%s states=%s author=%s",
            title, selected_state_names, author_id,
        )
        await state.clear()
        await callback.message.edit_text(
            "Рассылка по статусам создана.",
            reply_markup=mailings_menu_keyboard(),
        )
    else:
        cohort_type = data.get("cohort_type", "")
        selected_values = set(data.get("selected_cohorts", []))
        cohort_specs = [(cohort_type, val) for val in selected_values]
        await RuleDAO.create_cohort_rules(
            cohort_specs=cohort_specs,
            name=title,
            text=text_body,
            regularity=regularity,
            author_id=author_id,
        )
        logger.info(
            "Mailing created: kind=cohort name=%s type=%s values=%d author=%s",
            title, cohort_type, len(selected_values), author_id,
        )
        await state.clear()
        await callback.message.edit_text(
            "Рассылка по когортам создана.",
            reply_markup=mailings_menu_keyboard(),
        )


@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("Список доступных команд", reply_markup=back_to_menu_keyboard())
