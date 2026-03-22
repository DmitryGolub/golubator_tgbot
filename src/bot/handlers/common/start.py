from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

import logging

from src.dao.user import UserDAO
from src.dao.role import RoleDAO
from src.models.user import State
from datetime import datetime, timezone

from src.core.config import settings
from src.services.auth import AuthService
from src.utils.onboarding import schedule_onboarding_notifications

logger = logging.getLogger(__name__)

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

    # Link user to Notion page
    await _link_notion_page(user.id, username)

    await message.answer(WELCOME_TEXT)


async def _link_notion_page(telegram_id: int, username: str) -> None:
    if not settings.NOTION_TOKEN or not settings.NOTION_DATABASE_ID or not username:
        return

    from src.services.notion_client import NotionService

    notion = NotionService(settings.NOTION_TOKEN, settings.NOTION_DATABASE_ID)
    try:
        # Check if user already has notion_page_id
        existing = await UserDAO.find_one_or_none(telegram_id=telegram_id)
        if existing and existing.notion_page_id:
            return

        # Search by telegram_id first, then by username
        page = await notion.find_page_by_telegram_id(telegram_id)
        if not page:
            page = await notion.find_page_by_username(username)

        if page:
            page_id = page["id"]
            await UserDAO.update(telegram_id=telegram_id, notion_page_id=page_id)
            # Write telegram_id to Notion page
            await notion.update_page_properties(
                page_id, {"Telegram ID": {"number": telegram_id}}
            )
        else:
            # Create new page in Notion
            new_page = await notion.create_page(username, telegram_id)
            if new_page:
                await UserDAO.update(
                    telegram_id=telegram_id, notion_page_id=new_page["id"]
                )
    except Exception:
        logger.exception("Failed to link Notion page for user %s", telegram_id)
    finally:
        await notion.close()
