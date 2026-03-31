from __future__ import annotations

import asyncio
from telethon import TelegramClient, events
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
        """Click an inline button and wait for the edited/new message."""
        # Set up a future to capture the edited message
        edit_future: asyncio.Future[Message] = asyncio.get_event_loop().create_future()
        msg_id = message.id

        async def on_edit(event):
            if event.message.id == msg_id and not edit_future.done():
                edit_future.set_result(event.message)

        async def on_new(event):
            if not edit_future.done():
                edit_future.set_result(event.message)

        # Register handlers for both edit and new message
        self._client.add_event_handler(on_edit, events.MessageEdited(chats=self._bot))
        self._client.add_event_handler(on_new, events.NewMessage(chats=self._bot))

        try:
            if text is not None:
                await message.click(text=text)
            elif index is not None:
                await message.click(index)
            else:
                raise ValueError("Specify text or index")

            return await asyncio.wait_for(edit_future, timeout=timeout)
        finally:
            self._client.remove_event_handler(on_edit)
            self._client.remove_event_handler(on_new)

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
