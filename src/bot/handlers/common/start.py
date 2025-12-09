from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart

from src.dao.user import UserDAO
from src.models.user import State, Role
from src.bot.filters.role import RoleFilter

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user

    user_id = user.id

    exist_user = await UserDAO.find_one_or_none(telegram_id=user_id)

    if exist_user:
        return await message.answer("Пользователь уже зарегистрирован")

    created_user = await UserDAO.add(
        telegram_id=user_id, username=user.username, name=user.full_name, role=Role.student, state=State.greeting
    )

    if not created_user:
        return await message.answer("Ошибка при создании пользователя")

    return await message.answer(f"Пользователь успешно создан {created_user.username}")
