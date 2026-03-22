from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command

import logging

from src.dao.user import UserDAO
from src.dao.role import RoleDAO
from src.models.user import State
from datetime import datetime, timezone

from src.core.config import settings
from src.services.auth import AuthService
from src.services.ui_text import UiTextService
from src.bot.keyboards.menu import menu_keyboard
from src.utils.onboarding import schedule_onboarding_notifications

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user

    user_id = user.id
    username = (user.username or "").strip()
    reg_time = datetime.now(timezone.utc)

    is_admin = user_id in settings.admin_ids

    existing_user = await UserDAO.find_one_or_none(telegram_id=user_id)

    if not existing_user:
        if is_admin:
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
        if is_admin and (
            existing_user.role_rel is None or existing_user.role_rel.name != "admin"
        ):
            admin_role = await RoleDAO.get_by_name("admin")
            if admin_role:
                await UserDAO.update(telegram_id=user_id, role_id=admin_role.id)
                await AuthService.invalidate_user(user_id)

    # Link user to Notion page
    await _link_notion_page(user.id, username)

    welcome = await UiTextService.get("start.welcome", name=user.first_name)
    await message.answer(welcome)

    # Show menu right after welcome
    permissions = await AuthService.get_user_permissions(user_id)
    if permissions:
        title = await UiTextService.get("menu.title")
        await message.answer(title, reply_markup=await menu_keyboard(permissions))


@router.message(Command("help"))
async def cmd_help(message: Message):
    permissions = await AuthService.get_user_permissions(message.from_user.id)
    if not permissions:
        text = await UiTextService.get("menu.access_denied")
        await message.answer(text)
        return

    title = await UiTextService.get("menu.title")
    await message.answer(title, reply_markup=await menu_keyboard(permissions))


async def _link_notion_page(telegram_id: int, username: str) -> None:
    if not settings.NOTION_TOKEN:
        return

    existing = await UserDAO.find_one_or_none(telegram_id=telegram_id)
    if existing and existing.notion_page_id:
        return

    try:
        from src.services.notion import (
            NotionClient,
            NotionDatabaseUnavailableError,
            NotionMenteeRepo,
            NotionMentorRepo,
        )

        # 1. Search in Менторская база
        if settings.NOTION_MENTOR_DB_ID:
            mentor_client = NotionClient(settings.NOTION_TOKEN, settings.NOTION_MENTOR_DB_ID)
            try:
                mentor_repo = NotionMentorRepo(mentor_client)
                mentor = await mentor_repo.find_by_telegram_id(telegram_id)
                if mentor:
                    await UserDAO.update(
                        telegram_id=telegram_id,
                        notion_page_id=mentor.page_id,
                        notion_source_db="mentor",
                    )
                    await mentor_repo.update_telegram_id(mentor.page_id, telegram_id)
                    return
            except NotionDatabaseUnavailableError:
                logger.warning("Mentor DB unavailable, skipping for user %s", telegram_id)
            finally:
                await mentor_client.close()

        # 2. Search in Голубиная база
        mentee_db_id = settings.NOTION_MENTEE_DB_ID or settings.NOTION_DATABASE_ID
        if mentee_db_id:
            mentee_client = NotionClient(settings.NOTION_TOKEN, mentee_db_id)
            try:
                mentee_repo = NotionMenteeRepo(mentee_client)

                mentee = await mentee_repo.find_by_telegram_id(telegram_id)
                if not mentee and username:
                    mentee = await mentee_repo.find_by_username(username)

                if mentee:
                    await UserDAO.update(
                        telegram_id=telegram_id,
                        notion_page_id=mentee.page_id,
                        notion_source_db="mentee",
                    )
                    await mentee_repo.update_telegram_id(mentee.page_id, telegram_id)
                    return

                # 3. Not found anywhere — create in Голубиная база
                if username:
                    page_id = await mentee_repo.create_page(username, telegram_id)
                    if page_id:
                        await UserDAO.update(
                            telegram_id=telegram_id,
                            notion_page_id=page_id,
                            notion_source_db="mentee",
                        )
            except NotionDatabaseUnavailableError:
                logger.warning("Mentee DB unavailable, skipping for user %s", telegram_id)
            finally:
                await mentee_client.close()
    except Exception:
        logger.exception("Failed to link Notion page for user %s", telegram_id)
