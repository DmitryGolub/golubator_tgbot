import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from src.bot.handlers.common.start import router as start_router
from src.bot.handlers.common.menu import router as menu_router
from src.bot.handlers.cohort.create import router as cohort_create_router
from src.bot.handlers.cohort.delete import router as cohort_delete_router
from src.bot.handlers.cohort.edit import router as cohort_edit_router
from src.bot.handlers.cohort.list import router as cohort_list_router
from src.bot.handlers.user.list import router as user_router
from src.bot.handlers.user.update_user import router as update_user_fsm_router
from src.bot.handlers.meeting import router as meeting_router
from src.bot.handlers.rbac.manage_roles import router as rbac_router
from src.bot.handlers.survey_builder import router as survey_builder_router
from src.bot.handlers.dynamic_survey import router as dynamic_survey_router
from src.bot.handlers.trigger_rules import router as trigger_rules_router
from src.bot.handlers.mentor_stats import router as mentor_stats_router
from src.bot.handlers.export_feedback import router as export_feedback_router
from src.bot.handlers.tags import router as tags_router

from src.bot.middlewares.logging_middleware import LoggingMiddleware
from src.core.config import settings
from src.core.healthcheck import start_health_server
from src.core.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def main():
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    logger.info(
        "Starting bot: log_level=%s, log_format=%s, db_host=%s, redis=%s, admins=%d",
        settings.LOG_LEVEL,
        settings.LOG_FORMAT,
        settings.DB_HOST,
        settings.REDIS_HOST,
        len(settings.admin_ids),
    )
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(LoggingMiddleware())

    dp.include_routers(
        start_router,
        menu_router,
        cohort_create_router,
        cohort_list_router,
        cohort_delete_router,
        cohort_edit_router,
        user_router,
        update_user_fsm_router,
        meeting_router,
        rbac_router,
        survey_builder_router,
        dynamic_survey_router,
        trigger_rules_router,
        mentor_stats_router,
        export_feedback_router,
        tags_router,
    )

    health_runner = await start_health_server()

    dp.startup.register(_set_bot_commands)
    dp.startup.register(_initial_sync)
    try:
        await dp.start_polling(bot)
    finally:
        await health_runner.cleanup()


async def _initial_sync(**kwargs) -> None:
    from src.celery_app import celery_app

    await asyncio.to_thread(celery_app.send_task, "notion.backup_pull_users")
    await asyncio.to_thread(celery_app.send_task, "notion.backup_pull_events")
    await asyncio.to_thread(celery_app.send_task, "notion.sync_cohorts")
    logger.info("Initial sync tasks dispatched to Celery")


async def _set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="end_call", description="Завершить активный созвон"),
    ]
    await bot.set_my_commands(commands)


if __name__ == "__main__":
    asyncio.run(main())
