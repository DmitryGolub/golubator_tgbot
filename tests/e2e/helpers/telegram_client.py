from __future__ import annotations

import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.custom import Message


async def _send_with_flood_guard(conv, text: str):
    """Send message with FloodWait retry (raises AssertionError if wait > 120s)."""
    try:
        await conv.send_message(text)
    except FloodWaitError as e:
        if e.seconds > 120:
            raise AssertionError(
                f"Telegram FloodWait {e.seconds}s — too many messages sent"
            ) from e
        await asyncio.sleep(e.seconds)
        await conv.send_message(text)


class TelegramTestClient:
    """Wrapper over Telethon for E2E test convenience."""

    def __init__(self, client: TelegramClient, bot_username: str):
        self._client = client
        self._bot = bot_username

    async def send_command(self, command: str, timeout: float = 15) -> Message:
        """Send a command to the bot and get the first response."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await _send_with_flood_guard(conv, command)
            return await conv.get_response()

    async def send_command_multi(
        self, command: str, count: int = 2, timeout: float = 15
    ) -> list[Message]:
        """Send a command and get multiple responses (e.g. welcome + menu)."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await _send_with_flood_guard(conv, command)
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
        data: str | None = None,
        timeout: float = 15,
    ) -> Message:
        """Click an inline button and wait for the bot response (edit or new message).

        Uses polling approach: remembers last messages before click,
        then polls until a new/edited message appears.

        Args:
            text: Match button by display text (first match — ambiguous if duplicates).
            index: Match button by position index.
            data: Match button by callback_data (exact match — unambiguous).
        """
        # Remember state before click
        old_messages = await self._client.get_messages(self._bot, limit=3)
        old_snapshots = {
            m.id: (m.text, m.edit_date, m.reply_markup) for m in old_messages
        }
        max_old_id = max(m.id for m in old_messages) if old_messages else 0

        # Perform click
        if data is not None:
            await message.click(data=data.encode() if isinstance(data, str) else data)
        elif text is not None:
            await message.click(text=text)
        elif index is not None:
            await message.click(index)
        else:
            raise ValueError("Specify text, index, or data")

        # Poll for changes
        deadline = asyncio.get_event_loop().time() + timeout
        interval = 0.1
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(interval)
            interval = min(interval * 2, 0.5)
            new_messages = await self._client.get_messages(self._bot, limit=5)
            for m in new_messages:
                # New message appeared
                if m.id > max_old_id:
                    return m
                # Existing message was edited
                if m.id in old_snapshots:
                    old_text, old_edit_date, old_markup = old_snapshots[m.id]
                    if m.text != old_text:
                        return m
                    if m.edit_date != old_edit_date:
                        return m

        raise TimeoutError(
            f"No response from bot within {timeout}s after clicking button"
        )

    async def send_text_in_fsm(self, text: str, timeout: float = 15) -> Message:
        """Send text in an FSM dialog and get the next prompt/confirmation."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await _send_with_flood_guard(conv, text)
            return await conv.get_response()

    async def fsm_dialog(self, steps: list[str], timeout: float = 15) -> list[Message]:
        """Run an FSM dialog: send a series of messages, collect all responses."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            responses = []
            for step in steps:
                await _send_with_flood_guard(conv, step)
                responses.append(await conv.get_response())
            return responses

    async def snapshot_last_message_id(self) -> int:
        """Capture the current last message id for later use with wait_for_message_after."""
        messages = await self._client.get_messages(self._bot, limit=1)
        return max((m.id for m in messages), default=0)

    async def wait_for_message_after(
        self, after_id: int, timeout: float = 15
    ) -> Message:
        """Wait for a message with id > after_id.

        Use with snapshot_last_message_id() taken BEFORE the action that triggers
        the expected message, to avoid race conditions.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        interval = 0.1
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(interval)
            interval = min(interval * 2, 0.5)
            new_messages = await self._client.get_messages(self._bot, limit=5)
            for m in new_messages:
                if m.id > after_id:
                    return m
        raise asyncio.TimeoutError(
            f"No new message from bot within {timeout}s (after_id={after_id})"
        )

    async def wait_for_message(self, timeout: float = 15) -> Message:
        """Wait for an incoming message from the bot (for notifications/triggers).

        Uses polling: remembers the latest message id, then polls until a new one appears.
        """
        old_messages = await self._client.get_messages(self._bot, limit=1)
        max_old_id = max((m.id for m in old_messages), default=0)
        deadline = asyncio.get_event_loop().time() + timeout
        interval = 0.1
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(interval)
            interval = min(interval * 2, 0.5)
            new_messages = await self._client.get_messages(self._bot, limit=3)
            for m in new_messages:
                if m.id > max_old_id:
                    return m
        raise asyncio.TimeoutError(f"No new message from bot within {timeout}s")

    async def press_callback(
        self,
        callback_data: str,
        button_text: str = "→",
        timeout: float = 15,
    ) -> Message:
        """Trigger an arbitrary callback_data by sending a bot message with an inline button.

        Steps:
        1. Bot API sends a message to the user with an inline button carrying callback_data
        2. Telethon clicks that button
        3. Bot handles the callback and edits/sends a response

        Useful for triggering callbacks not reachable via menu navigation (e.g. my_surveys).
        """
        import os

        import httpx

        # Step 1: Send message with inline button via Bot API
        me = await self._client.get_me()
        token = os.environ["BOT_TOKEN"]
        keyboard = {
            "inline_keyboard": [[{"text": button_text, "callback_data": callback_data}]]
        }
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": me.id,
                    "text": "⏳",
                    "reply_markup": keyboard,
                },
            )
            resp.raise_for_status()

        # Step 2: Wait for the message to appear and click the button
        await asyncio.sleep(1)
        messages = await self._client.get_messages(self._bot, limit=3)
        target = None
        for m in messages:
            if m.reply_markup and hasattr(m.reply_markup, "rows"):
                for row in m.reply_markup.rows:
                    for btn in row.buttons:
                        if btn.data and btn.data.decode() == callback_data:
                            target = m
                            break
            if target:
                break

        if target is None:
            raise ValueError(
                f"Could not find bot message with button '{callback_data}'"
            )

        return await self.click_button(target, text=button_text, timeout=timeout)

    async def get_last_messages(self, limit: int = 5) -> list[Message]:
        """Get last messages from the bot chat."""
        return await self._client.get_messages(self._bot, limit=limit)

    @property
    def raw(self) -> TelegramClient:
        return self._client
