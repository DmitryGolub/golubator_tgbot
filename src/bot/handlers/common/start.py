from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

from src.dao.user import UserDAO
from src.dao.role import RoleDAO
from src.models.user import State
from datetime import datetime, timezone

from src.core.config import settings
from src.services.auth import AuthService
from src.utils.onboarding import schedule_onboarding_notifications

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
    reg_time = datetime.now(timezone.utc)

    is_admin_username = username.lower() in settings.admin_usernames if username else False

    existing_user = await UserDAO.find_one_or_none(telegram_id=user_id)

    if not existing_user:
        if is_admin_username:
            role_obj = await RoleDAO.get_by_name("admin")
        else:
            role_obj = await RoleDAO.get_by_name("student")

        created_user = await UserDAO.add(
            telegram_id=user_id,
            username=user.username,
            name=user.full_name,
            role_id=role_obj.id if role_obj else None,
            state=State.greeting,
            registered_at=reg_time,
        )
        if created_user:
            await schedule_onboarding_notifications(created_user, base_time=reg_time)
    else:
        # keep admin role in sync with env setting
        if is_admin_username and (
            existing_user.role_rel is None or existing_user.role_rel.name != "admin"
        ):
            admin_role = await RoleDAO.get_by_name("admin")
            if admin_role:
                await UserDAO.update(telegram_id=user_id, role_id=admin_role.id)
                await AuthService.invalidate_user(user_id)

    await message.answer(WELCOME_TEXT)
