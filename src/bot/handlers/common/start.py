from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

from src.dao.user import UserDAO
from src.models.user import State, Role
from src.core.config import settings

router = Router()


WELCOME_TEXT = (
    "<b>Привет!</b>\n\n"
    "Я буду напоминать вам о занятиях и присылать полезную информацию.\n"
    "Через команду <b>/menu</b> можно открыть главное меню, "
    "посмотреть свои данные и доступные действия.\n\n"
    "Если что-то не работает — напишите куратору."
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user

    user_id = user.id
    username = (user.username or "").strip()

    is_admin_username = username.lower() in settings.admin_usernames if username else False

    existing_user = await UserDAO.find_one_or_none(telegram_id=user_id)

    if not existing_user:
        await UserDAO.add(
            telegram_id=user_id,
            username=user.username,
            name=user.full_name,
            role=Role.admin if is_admin_username else Role.student,
            state=State.greeting,
        )
    else:
        # keep admin role in sync with env setting
        if is_admin_username and existing_user.role != Role.admin:
            await UserDAO.update(telegram_id=user_id, role=Role.admin)

    await message.answer(WELCOME_TEXT)
