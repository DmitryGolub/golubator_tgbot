from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from src.bot.filters.role import RoleFilter
from src.bot.keyboards.mailings import (
    mailings_menu_keyboard,
    mailing_type_keyboard,
    select_users_keyboard,
    select_states_keyboard,
    regularity_keyboard,
    delete_mailings_keyboard,
)
from src.bot.keyboards.menu import back_to_menu_keyboard
from src.bot.callbacks.rule import (
    MailingTypeCB,
    ToggleUserCB,
    ToggleStateCB,
    ChooseRegularityCB,
    MailingFinishUsersCB,
    MailingFinishStatesCB,
    ToggleDeleteUserRuleCB,
    ToggleDeleteStateRuleCB,
    DeleteMailingsFinishCB,
)
from src.bot.states.mailings import MailingFSM
from src.dao.user import UserDAO
from src.dao.rule import RuleDAO
from src.models.user import Role, State
from src.models.rule import Regularity

router = Router(name="mailings")
router.message.filter(RoleFilter([Role.admin]))
router.callback_query.filter(RoleFilter([Role.admin]))


REGULARITY_TO_OFFSET = {
    Regularity.day: 1,
    Regularity.week: 7,
    Regularity.fortnight: 14,
    Regularity.month: 30,
}


@router.callback_query(RoleFilter([Role.admin]), F.data == "menu_mailings")
async def cb_menu_mailings(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("👥 Меню Рассылок", reply_markup=mailings_menu_keyboard())


@router.callback_query(RoleFilter([Role.admin]), F.data == "mailings_menu")
async def cb_mailings_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("👥 Меню Рассылок", reply_markup=mailings_menu_keyboard())


@router.callback_query(RoleFilter([Role.admin]), F.data == "mailings_list")
async def cb_mailings_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()

    user_rules = await RuleDAO.list_user_rules()
    state_rules = await RuleDAO.list_state_rules()

    parts = ["<b>Список рассылок:</b>", ""]
    if user_rules:
        parts.append("<b>Индивидуальные:</b>")
        for rule in user_rules:
            parts.append(
                f"• Название: {rule.name or '—'}\n"
                f"  Пользователь: @{rule.user.username} ({rule.user.name})\n"
                f"  Регулярность: {rule.regularity.value}\n"
                f"  Текст: {rule.text or '—'}"
            )
    if state_rules:
        parts.append("")
        parts.append("<b>По статусам:</b>")
        for rule in state_rules:
            parts.append(
                f"• Название: {rule.name or '—'}\n"
                f"  Статус: {rule.user_state.value}\n"
                f"  Регулярность: {rule.regularity.value}\n"
                f"  Текст: {rule.text or '—'}"
            )

    if not user_rules and not state_rules:
        parts = ["<b>Список рассылок пуст.</b>"]

    await callback.message.edit_text("\n".join(parts), reply_markup=mailings_menu_keyboard())


@router.callback_query(RoleFilter([Role.admin]), F.data == "mailings_add")
async def cb_mailings_add(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(MailingFSM.choosing_type)
    await callback.answer()
    await callback.message.edit_text("Выберите тип рассылки:", reply_markup=mailing_type_keyboard())


@router.callback_query(RoleFilter([Role.admin]), MailingTypeCB.filter())
async def cb_choose_type(callback: CallbackQuery, callback_data: MailingTypeCB, state: FSMContext):
    kind = callback_data.kind
    await state.update_data(kind=kind)
    await state.set_state(MailingFSM.waiting_title)
    await callback.answer()
    await callback.message.edit_text("Введите название рассылки:")


@router.callback_query(RoleFilter([Role.admin]), F.data == "mailings_delete")
async def cb_mailings_delete(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(MailingFSM.deleting_rules)
    await state.update_data(del_user_rules=[], del_state_rules=[])

    user_rules = await RuleDAO.list_user_rules()
    state_rules = await RuleDAO.list_state_rules()

    await callback.answer()
    await callback.message.edit_text(
        "Выберите рассылки для удаления:",
        reply_markup=delete_mailings_keyboard(user_rules, state_rules, set(), set()),
    )


@router.callback_query(
    RoleFilter([Role.admin]),
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

    await callback.answer()
    await callback.message.edit_text(
        "Выберите рассылки для удаления:",
        reply_markup=delete_mailings_keyboard(user_rules, state_rules, sel_users, set(data.get("del_state_rules", []))),
    )


@router.callback_query(
    RoleFilter([Role.admin]),
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

    await callback.answer()
    await callback.message.edit_text(
        "Выберите рассылки для удаления:",
        reply_markup=delete_mailings_keyboard(user_rules, state_rules, set(data.get("del_user_rules", [])), sel_states),
    )


@router.callback_query(
    RoleFilter([Role.admin]),
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

    if not sel_users and not sel_states:
        await callback.answer("Нужно выбрать хотя бы одну рассылку.", show_alert=True)
        return

    if sel_users:
        await RuleDAO.delete_user_rules(sel_users)
    if sel_states:
        await RuleDAO.delete_state_rules(sel_states)

    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "Выбранные рассылки удалены.",
        reply_markup=mailings_menu_keyboard(),
    )


@router.message(RoleFilter([Role.admin]), StateFilter(MailingFSM.waiting_title))
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
    else:
        await state.update_data(selected_states=[])
        await state.set_state(MailingFSM.choosing_states)
        await message.answer(
            "Выберите статусы (можно несколько), затем нажмите «Готово».",
            reply_markup=select_states_keyboard(set()),
        )


@router.callback_query(RoleFilter([Role.admin]), StateFilter(MailingFSM.choosing_users), ToggleUserCB.filter())
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


@router.callback_query(RoleFilter([Role.admin]), StateFilter(MailingFSM.choosing_users), MailingFinishUsersCB.filter())
async def cb_finish_users(callback: CallbackQuery, callback_data: MailingFinishUsersCB, state: FSMContext):
    data = await state.get_data()
    selected: set[int] = set(data.get("selected_users", set()))
    if not selected:
        await callback.answer("Нужно выбрать хотя бы одного пользователя.", show_alert=True)
        return

    await state.set_state(MailingFSM.waiting_text)
    await callback.answer()
    await callback.message.edit_text("Введите текст рассылки:")


@router.callback_query(RoleFilter([Role.admin]), StateFilter(MailingFSM.choosing_states), ToggleStateCB.filter())
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


@router.callback_query(RoleFilter([Role.admin]), StateFilter(MailingFSM.choosing_states), MailingFinishStatesCB.filter())
async def cb_finish_states(callback: CallbackQuery, callback_data: MailingFinishStatesCB, state: FSMContext):
    data = await state.get_data()
    selected_names = set(data.get("selected_states", []))
    if not selected_names:
        await callback.answer("Нужно выбрать хотя бы один статус.", show_alert=True)
        return
    selected_states = {State(name) for name in selected_names}

    await state.set_state(MailingFSM.waiting_text)
    await callback.answer()
    await callback.message.edit_text("Введите текст рассылки:")


@router.message(RoleFilter([Role.admin]), StateFilter(MailingFSM.waiting_text))
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


@router.callback_query(RoleFilter([Role.admin]), StateFilter(MailingFSM.choosing_regularity), ChooseRegularityCB.filter())
async def cb_choose_regularity(
    callback: CallbackQuery,
    callback_data: ChooseRegularityCB,
    state: FSMContext,
):
    data = await state.get_data()
    kind = data.get("kind")
    title = data.get("title")
    text_body = data.get("text")

    full_text = f"{title}\n\n{text_body}"
    regularity = callback_data.regularity
    author_id = callback.from_user.id

    await callback.answer()

    if kind == "individual":
        selected: set[int] = set(data.get("selected_users", set()))
        await RuleDAO.create_user_rules(
            user_ids=selected,
            name=title,
            text=full_text,
            regularity=regularity,
            author_id=author_id,
        )
        await state.clear()
        await callback.message.edit_text(
            "Индивидуальная рассылка создана.",
            reply_markup=mailings_menu_keyboard(),
        )
    else:
        selected_state_names = set(data.get("selected_states", []))
        selected_states = {State(name) for name in selected_state_names}
        offset_days = REGULARITY_TO_OFFSET.get(regularity, None)
        await RuleDAO.create_state_rules(
            states=selected_states,
            name=title,
            text=full_text,
            regularity=regularity,
            author_id=author_id,
            offset_days=offset_days,
        )
        await state.clear()
        await callback.message.edit_text(
            "Рассылка по статусам создана.",
            reply_markup=mailings_menu_keyboard(),
        )


@router.callback_query(RoleFilter([Role.admin]), F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("Список доступных команд", reply_markup=back_to_menu_keyboard())
