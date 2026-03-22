import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage

from src.bot.handlers.common.start import router as start_router
from src.bot.handlers.common.menu import router as menu_router
from src.bot.handlers.cohort.create import router as cohort_create_router
from src.bot.handlers.cohort.delete import router as cohort_delete_router
from src.bot.handlers.cohort.edit import router as cohort_edit_router
from src.bot.handlers.cohort.list import router as cohort_list_router
from src.bot.handlers.user.list import router as user_router
from src.bot.handlers.user.update_user import router as update_user_fsm_router
from src.bot.handlers.meeting import router as meeting_router
from src.bot.handlers.mentor_feedback import router as mentor_feedback_router
from src.bot.handlers.mailings import router as mailings_router
from src.bot.handlers.mentor_self_review import router as mentor_self_review_router
from src.bot.handlers.rbac.manage_roles import router as rbac_router
from src.bot.handlers.survey import router as survey_router
from src.bot.handlers.survey_builder import router as survey_builder_router
from src.bot.handlers.dynamic_survey import router as dynamic_survey_router

from src.core.config import settings


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)

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
        mentor_feedback_router,
        mailings_router,
        mentor_self_review_router,
        rbac_router,
        survey_router,
        survey_builder_router,
        dynamic_survey_router,
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
