import asyncio
import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command

from src.dao.user import UserDAO
from src.dao.role import RoleDAO
from src.dao.mentor import MentorDAO
from src.dao.mentee import MenteeDAO
from src.models.user import User
from datetime import datetime, timezone

from src.core.config import settings
from src.services.auth import AuthService
from src.services.ui_text import UiTextService
from src.bot.keyboards.menu import menu_keyboard
from src.utils.onboarding import schedule_onboarding_notifications

logger = logging.getLogger(__name__)

router = Router()

_background_tasks: set[asyncio.Task] = set()


async def _ensure_user(tg_user) -> User:
    """Create or update User record (telegram data only). Returns User."""
    user_id = tg_user.id
    is_admin = user_id in settings.admin_ids

    existing = await UserDAO.find_one_or_none(telegram_id=user_id)

    if not existing:
        role_obj = await RoleDAO.get_by_name("admin" if is_admin else "student")
        now = datetime.now(timezone.utc)
        created = await UserDAO.add(
            telegram_id=user_id,
            username=tg_user.username,
            name=tg_user.full_name,
            role_id=role_obj.id if role_obj else None,
            registered_at=now,
        )
        if created:
            logger.info(
                "New user registered: tg=%s role=%s",
                user_id,
                "admin" if is_admin else "student",
            )
            await schedule_onboarding_notifications(created)
        return created
    else:
        if is_admin and (
            existing.role_rel is None or existing.role_rel.name != "admin"
        ):
            admin_role = await RoleDAO.get_by_name("admin")
            if admin_role:
                await UserDAO.update(telegram_id=user_id, role_id=admin_role.id)
                await AuthService.invalidate_user(user_id)
        return existing


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user

    await _ensure_user(user)

    username = (user.username or "").strip()

    task = asyncio.create_task(_link_notion_page(user.id, username))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    welcome = await UiTextService.get("start.welcome", name=user.first_name)
    await message.answer(welcome)

    permissions = await AuthService.get_user_permissions(user.id)
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


async def _merge_placeholder(telegram_id: int, placeholder_id: int) -> None:
    """Relink Mentor/Mentee from placeholder to real User, then delete placeholder."""
    mentor = await MentorDAO.find_by_telegram_id(placeholder_id)
    if mentor:
        await MentorDAO.update(mentor.id, telegram_id=telegram_id)
    mentee = await MenteeDAO.find_by_telegram_id(placeholder_id)
    if mentee:
        await MenteeDAO.update(mentee.id, telegram_id=telegram_id)
    await UserDAO.delete(telegram_id=placeholder_id)


async def _link_notion_page(telegram_id: int, username: str) -> None:
    if not settings.NOTION_TOKEN:
        return

    mentor_record = await MentorDAO.find_by_telegram_id(telegram_id)
    if mentor_record and mentor_record.notion_page_id:
        return

    mentee_record = await MenteeDAO.find_by_telegram_id(telegram_id)
    if mentee_record and mentee_record.notion_page_id:
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
            mentor_client = NotionClient(
                settings.NOTION_TOKEN, settings.NOTION_MENTOR_DB_ID
            )
            try:
                mentor_repo = NotionMentorRepo(mentor_client)
                notion_mentor = await mentor_repo.find_by_telegram_id(telegram_id)
                if notion_mentor:
                    # Check if there's a placeholder mentor for this notion page
                    existing_mentor = await MentorDAO.find_by_notion_page_id(
                        notion_mentor.page_id
                    )
                    if (
                        existing_mentor
                        and existing_mentor.telegram_id is not None
                        and existing_mentor.telegram_id < 0
                    ):
                        await _merge_placeholder(
                            telegram_id, existing_mentor.telegram_id
                        )
                    elif mentor_record:
                        await MentorDAO.update(
                            mentor_record.id, telegram_id=telegram_id
                        )
                    else:
                        await MentorDAO.add(
                            telegram_id=telegram_id,
                            notion_page_id=notion_mentor.page_id,
                        )
                    await mentor_repo.update_telegram_id(
                        notion_mentor.page_id, telegram_id
                    )
                    logger.info(
                        "Notion mentor linked: user=%s page=%s",
                        telegram_id,
                        notion_mentor.page_id,
                    )
                    return
            except NotionDatabaseUnavailableError:
                logger.warning(
                    "Mentor DB unavailable, skipping for user %s", telegram_id
                )
            finally:
                await mentor_client.close()

        # 2. Search in Голубиная база
        mentee_db_id = settings.NOTION_MENTEE_DB_ID or settings.NOTION_DATABASE_ID
        if mentee_db_id:
            mentee_client = NotionClient(settings.NOTION_TOKEN, mentee_db_id)
            try:
                mentee_repo = NotionMenteeRepo(mentee_client)

                notion_mentee = await mentee_repo.find_by_telegram_id(telegram_id)
                if not notion_mentee and username:
                    notion_mentee = await mentee_repo.find_by_username(username)

                if notion_mentee:
                    # Check if there's a placeholder mentee for this notion page
                    existing_mentee = await MenteeDAO.find_by_notion_page_id(
                        notion_mentee.page_id
                    )
                    if (
                        existing_mentee
                        and existing_mentee.telegram_id is not None
                        and existing_mentee.telegram_id < 0
                    ):
                        await _merge_placeholder(
                            telegram_id, existing_mentee.telegram_id
                        )
                    elif mentee_record:
                        await MenteeDAO.update(
                            mentee_record.id, telegram_id=telegram_id
                        )
                    else:
                        await MenteeDAO.add(
                            telegram_id=telegram_id,
                            notion_page_id=notion_mentee.page_id,
                            doc_name=f"@{username}" if username else None,
                        )
                    await mentee_repo.update_telegram_id(
                        notion_mentee.page_id, telegram_id
                    )
                    logger.info(
                        "Notion mentee linked: user=%s page=%s",
                        telegram_id,
                        notion_mentee.page_id,
                    )
                    return

                # 3. Not found anywhere — create in Голубиная база
                if username:
                    page_id = await mentee_repo.create_page(username, telegram_id)
                    if page_id:
                        await MenteeDAO.add(
                            telegram_id=telegram_id,
                            notion_page_id=page_id,
                            doc_name=f"@{username}",
                        )
                        logger.info(
                            "Notion mentee created: user=%s page=%s",
                            telegram_id,
                            page_id,
                        )
            except NotionDatabaseUnavailableError:
                logger.warning(
                    "Mentee DB unavailable, skipping for user %s", telegram_id
                )
            finally:
                await mentee_client.close()
    except Exception as exc:
        logger.error("Failed to link Notion page for user %s: %s", telegram_id, exc)
