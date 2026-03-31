from __future__ import annotations

import asyncio
from telethon import TelegramClient
from telethon.tl.custom import Message


class TelegramTestClient:
    """Wrapper over Telethon for E2E test convenience."""

    def __init__(self, client: TelegramClient, bot_username: str):
        self._client = client
        self._bot = bot_username

    async def send_command(self, command: str, timeout: float = 15) -> Message:
        """Send a command to the bot and get the first response."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await conv.send_message(command)
            return await conv.get_response()

    async def send_command_multi(
        self, command: str, count: int = 2, timeout: float = 15
    ) -> list[Message]:
        """Send a command and get multiple responses (e.g. welcome + menu)."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await conv.send_message(command)
            responses = []
            for _ in range(count):
                try:
                    responses.append(await conv.get_response())
                except asyncio.TimeoutError:
                    break
            return responses

    async def click_button(
        self,
        message: Message,
        text: str | None = None,
        index: int | None = None,
        timeout: float = 15,
    ) -> Message:
        """Click an inline button and wait for the bot response (edit or new message).

        Uses polling approach: remembers last messages before click,
        then polls until a new/edited message appears.
        """
        # Remember state before click
        old_messages = await self._client.get_messages(self._bot, limit=3)
        old_ids_texts = {m.id: (m.text, m.date) for m in old_messages}
        max_old_id = max(m.id for m in old_messages) if old_messages else 0

        # Perform click
        if text is not None:
            await message.click(text=text)
        elif index is not None:
            await message.click(index)
        else:
            raise ValueError("Specify text or index")

        # Poll for changes
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.5)
            new_messages = await self._client.get_messages(self._bot, limit=5)
            for m in new_messages:
                # New message appeared
                if m.id > max_old_id:
                    return m
                # Existing message was edited (text changed)
                if m.id in old_ids_texts:
                    old_text, old_date = old_ids_texts[m.id]
                    if (
                        m.text != old_text
                        or m.edit_date is not None
                        and (m.id not in old_ids_texts or m.edit_date != old_date)
                    ):
                        return m

        raise TimeoutError(
            f"No response from bot within {timeout}s after clicking button"
        )

    async def send_text_in_fsm(self, text: str, timeout: float = 15) -> Message:
        """Send text in an FSM dialog and get the next prompt/confirmation."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await conv.send_message(text)
            return await conv.get_response()

    async def fsm_dialog(self, steps: list[str], timeout: float = 15) -> list[Message]:
        """Run an FSM dialog: send a series of messages, collect all responses."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            responses = []
            for step in steps:
                await conv.send_message(step)
                responses.append(await conv.get_response())
            return responses

    async def wait_for_message(self, timeout: float = 30) -> Message:
        """Wait for an incoming message from the bot (for notifications/triggers)."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            return await conv.get_response()

    async def get_last_messages(self, limit: int = 5) -> list[Message]:
        """Get last messages from the bot chat."""
        return await self._client.get_messages(self._bot, limit=limit)

    @property
    def raw(self) -> TelegramClient:
        return self._client
