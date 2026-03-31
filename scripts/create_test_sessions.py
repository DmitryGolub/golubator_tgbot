import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv(".env.test")


async def main():
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    for name, phone_key in [
        ("account1", "TEST_ACCOUNT_1_PHONE"),
        ("account2", "TEST_ACCOUNT_2_PHONE"),
    ]:
        client = TelegramClient(f"tests/e2e/sessions/{name}", api_id, api_hash)
        await client.start(phone=os.environ[phone_key])
        print(f"Session {name} created for {os.environ[phone_key]}")
        await client.disconnect()


asyncio.run(main())
