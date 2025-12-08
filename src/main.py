import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command

from src.core.config import settings


async def cmd_start(message: Message):
    await message.answer("Привет! Я простой бот на aiogram 😊")


async def echo_handler(message: Message):
    await message.answer(f"Ты написал: {message.text}")


async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(cmd_start, Command(commands=["start"]))
    dp.message.register(echo_handler, F.text)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())