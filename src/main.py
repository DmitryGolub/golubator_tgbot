import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage

from src.bot.handlers.common.start import router as start_router
from src.bot.handlers.common.menu import router as menu_router
from src.bot.handlers.user.list import router as user_router

from src.core.config import settings


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)

    dp.include_routers(
        start_router,
        menu_router,
        user_router,
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())