from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from src.bot.keyboards.menu import menu_keyboard
from src.bot.keyboards.user import user_actions_keyboard
from src.bot.keyboards.cohort import cohort_actions_keyboard

router = Router(name="menu")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(text="Список доступных команд", reply_markup=menu_keyboard())


@router.callback_query(F.data == "back_to_menu")
async def cb_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(text="Список доступных команд", reply_markup=menu_keyboard())


@router.callback_query(F.data == "menu_users")
async def cb_menu_users(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("👥 Меня Пользователей", reply_markup=user_actions_keyboard())


@router.callback_query(F.data == "menu_cohorts")
async def cb_menu_cohorts(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("👥 Меню Когорт", reply_markup=cohort_actions_keyboard())


@router.callback_query(F.data == "menu_mailings")
async def cb_menu_mailings(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("👥 Меню Рассылок")