from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

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
from src.models.user import User, State
from src.models.rule import Regularity, UserRule, StateRule


def mailings_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Список рассылок", callback_data="mailings_list")
    kb.button(text="Добавить рассылку", callback_data="mailings_add")
    kb.button(text="Удалить рассылку", callback_data="mailings_delete")
    kb.button(text="⬅️ Назад", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def mailing_type_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Индивидуальная", callback_data=MailingTypeCB(kind="individual").pack())
    kb.button(text="По статусам", callback_data=MailingTypeCB(kind="state").pack())
    kb.button(text="⬅️ Назад", callback_data="mailings_menu")
    kb.adjust(1)
    return kb.as_markup()


def select_users_keyboard(users: list[User], selected: set[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for u in users:
        mark = "✅ " if u.telegram_id in selected else ""
        kb.button(
            text=f"{mark}{u.name} @{u.username}",
            callback_data=ToggleUserCB(user_id=u.telegram_id).pack(),
        )
    kb.button(text="Готово", callback_data=MailingFinishUsersCB(done=True).pack())
    kb.button(text="❌ Отмена", callback_data="mailings_menu")
    kb.adjust(1)
    return kb.as_markup()


def select_states_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for st in State:
        mark = "✅ " if st.value in selected else ""
        kb.button(
            text=f"{mark}{st.value}",
            callback_data=ToggleStateCB(state=st).pack(),
        )
    kb.button(text="Готово", callback_data=MailingFinishStatesCB(done=True).pack())
    kb.button(text="❌ Отмена", callback_data="mailings_menu")
    kb.adjust(1)
    return kb.as_markup()


def regularity_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for reg in Regularity:
        kb.button(text=reg.value, callback_data=ChooseRegularityCB(regularity=reg).pack())
    kb.button(text="❌ Отмена", callback_data="mailings_menu")
    kb.adjust(1)
    return kb.as_markup()


def delete_mailings_keyboard(
    user_rules: list[UserRule],
    state_rules: list[StateRule],
    sel_users: set[int],
    sel_states: set[int],
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if user_rules:
        kb.button(text="— Пользовательские —", callback_data="noop")
        for rule in user_rules:
            mark = "✅ " if rule.id in sel_users else ""
            kb.button(
                text=f"{mark}{rule.name or rule.text[:20]}",
                callback_data=ToggleDeleteUserRuleCB(rule_id=rule.id).pack(),
            )
    if state_rules:
        kb.button(text="— По статусам —", callback_data="noop")
        for rule in state_rules:
            mark = "✅ " if rule.id in sel_states else ""
            kb.button(
                text=f"{mark}{rule.name or rule.text[:20]}",
                callback_data=ToggleDeleteStateRuleCB(rule_id=rule.id).pack(),
            )

    kb.button(text="Удалить выбранные", callback_data=DeleteMailingsFinishCB(done=True).pack())
    kb.button(text="❌ Отмена", callback_data="mailings_menu")
    kb.adjust(1)
    return kb.as_markup()
